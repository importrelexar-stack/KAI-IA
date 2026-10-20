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

/**
 * Notifica las acciones de KAI que esperan autorización. La notificación sólo abre la app:
 * aprobar requiere ver el detalle de la acción (no se aprueba a ciegas desde la notificación).
 */
class ApprovalWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    companion object {
        const val CHANNEL = "approvals"
        const val EXTRA_OPEN_TASKS = "open_tasks"

        fun notifyNew(context: Context, store: SecureStore, tasks: List<KaiTask>) {
            val waiting = tasks.filter { it.awaitingApproval }
            val seen = store.notifiedTasks
            val fresh = waiting.filter { it.id !in seen }
            if (fresh.isEmpty()) return
            store.notifiedTasks = seen + fresh.map { it.id }
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
                android.os.Build.VERSION.SDK_INT >= 33
            ) return
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
            val tasks = KaiClient(session.baseUrl, session.token).tasks("awaiting_approval")
            notifyNew(applicationContext, store, tasks)
            Result.success()
        } catch (e: KaiApiException) {
            // PC apagada o fuera de la red: se reintenta en el próximo ciclo
            Result.success()
        } catch (e: IllegalArgumentException) {
            Result.success()
        }
    }
}
