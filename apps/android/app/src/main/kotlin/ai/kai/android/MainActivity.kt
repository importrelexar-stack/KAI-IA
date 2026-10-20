package ai.kai.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import ai.kai.android.ui.KaiRoot
import ai.kai.android.ui.KaiTheme

class MainActivity : ComponentActivity() {
    private val vm: KaiViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleIntent(intent)
        setContent { KaiTheme { KaiRoot(vm) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(ApprovalWorker.EXTRA_OPEN_TASKS, false) == true) {
            vm.tab = Tab.Tasks
            vm.refreshTasks()
        }
    }
}
