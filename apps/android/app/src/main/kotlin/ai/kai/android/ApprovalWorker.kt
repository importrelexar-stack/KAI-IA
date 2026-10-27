package ai.kai.android

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import ai.kai.core.KaiApiException
import ai.kai.core.KaiClient
import ai.kai.core.KaiTask
import ai.kai.core.Routine

/**
 * Notifica las acciones de KAI que esperan autorización. La notificación sólo abre la app:
 * aprobar requiere ver el detalle de la acción (no se aprueba a ciegas desde la notificación).
 */
class ApprovalWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    companion object {
        const val CHANNEL = "approvals"
        const val CHANNEL_ROUTINES = "routines"
        const val EXTRA_OPEN_TASKS = "open_tasks"
        const val EXTRA_OPEN_CONVERSATION = "open_conversation"

        private fun canNotify(context: Context): Boolean =
            android.os.Build.VERSION.SDK_INT < 33 ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

        /** Avisa las rutinas que terminaron desde la última revisión (la primera vez sólo registra el estado). */
        fun notifyRoutines(context: Context, store: SecureStore, routines: List<Routine>) {
            val seen = store.seenRoutineRuns
            val current = routines.filter { it.lastRunAt != null && it.lastStatus != "running" }
                .associate { it.id to it.lastRunAt!! }
            store.seenRoutineRuns = current
            if (seen == null || !canNotify(context)) return
            routines.filter { r -> r.lastRunAt != null && r.lastStatus != "running" && seen[r.id] != r.lastRunAt }
                .forEach { r ->
                    val open = PendingIntent.getActivity(
                        context, r.id.hashCode(),
                        Intent(context, MainActivity::class.java).putExtra(EXTRA_OPEN_CONVERSATION, r.conversationId)
                            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
                    )
                    val ok = r.lastStatus == "ok"
                    val n = NotificationCompat.Builder(context, CHANNEL_ROUTINES)
                        .setSmallIcon(R.drawable.ic_notification)
                        .setContentTitle(if (ok) "Rutina lista: ${r.name}" else "La rutina «${r.name}» falló")
                        .setContentText(if (ok) "Tocá para ver el resultado" else (r.lastError ?: "Revisá KAI en la PC"))
                        .setContentIntent(open)
                        .setAutoCancel(true)
                        .build()
                    try {
                        NotificationManagerCompat.from(context).notify(2000 + (r.id.hashCode() and 0xFFF), n)
                    } catch (_: SecurityException) {
                    }
                }
        }

        fun notifyNew(context: Context, store: SecureStore, tasks: List<KaiTask>) {
            val waiting = tasks.filter { it.awaitingApproval }
            val seen = store.notifiedTasks
            val fresh = waiting.filter { it.id !in seen }
            if (fresh.isEmpty()) return
            store.notifiedTasks = seen + fresh.map { it.id }
            if (!canNotify(context)) return
            val open = PendingIntent.getActivity(
                context, 0,
                Intent(context, MainActivity::class.java).putExtra(EXTRA_OPEN_TASKS, true)
                    .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            val title = if (fresh.size == 1) "KAI necesita tu autorización" else "${fresh.size} acciones esperan tu autorización"
            val n = NotificationCompat.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(title)
                .setContentText(fresh.first().title)
                .setStyle(NotificationCompat.InboxStyle().also { s -> fresh.take(5).forEach { s.addLine(it.title) } })
                .setContentIntent(open)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .build()
            try {
                NotificationManagerCompat.from(context).notify(1001, n)
            } catch (_: SecurityException) {
            }
        }
    }

    override suspend fun doWork(): Result {
        val store = SecureStore(applicationContext)
        val session = store.load() ?: return Result.success()
        return try {
            val client = KaiClient(session.baseUrl, session.token)
            notifyNew(applicationContext, store, client.tasks("awaiting_approval"))
            notifyRoutines(applicationContext, store, client.routines())
            Result.success()
        } catch (e: KaiApiException) {
            // PC apagada o fuera de la red: se reintenta en el próximo ciclo
            Result.success()
        } catch (e: IllegalArgumentException) {
            Result.success()
        }
    }
}
