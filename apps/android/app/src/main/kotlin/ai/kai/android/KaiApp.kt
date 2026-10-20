package ai.kai.android

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class KaiApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(
            ApprovalWorker.CHANNEL, getString(R.string.channel_approvals), NotificationManager.IMPORTANCE_HIGH,
        ).apply { description = getString(R.string.channel_approvals_desc) }
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(channel)
        nm.createNotificationChannel(NotificationChannel(
            ApprovalWorker.CHANNEL_ROUTINES, getString(R.string.channel_routines), NotificationManager.IMPORTANCE_DEFAULT,
        ).apply { description = getString(R.string.channel_routines_desc) })
        if (SecureStore(this).load() != null) scheduleApprovalChecks()
    }

    /** Revisa cada 15 minutos (mínimo de Android) si hay acciones esperando autorización. */
    fun scheduleApprovalChecks() {
        val req = PeriodicWorkRequestBuilder<ApprovalWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("kai-approvals", ExistingPeriodicWorkPolicy.KEEP, req)
    }

    fun cancelApprovalChecks() = WorkManager.getInstance(this).cancelUniqueWork("kai-approvals")
}
