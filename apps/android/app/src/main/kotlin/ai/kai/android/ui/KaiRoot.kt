package ai.kai.android.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ai.kai.android.KaiViewModel
import ai.kai.android.Tab

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KaiRoot(vm: KaiViewModel) {
    val notifPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    val session = vm.session
    LaunchedEffect(session != null) {
        if (session != null && Build.VERSION.SDK_INT >= 33) notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
    if (session == null) {
        Scaffold { p -> PairScreen(vm, Modifier.padding(p)) }
        return
    }
    val waiting = vm.tasks.count { it.awaitingApproval }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("KAI") },
                navigationIcon = { androidx.compose.foundation.layout.Box(Modifier.padding(start = 14.dp, end = 6.dp)) { KaiOrb(28.dp, vm.busy) } },
                actions = {
                    val (label, color) = when (vm.online) {
                        true -> "Conectado" to KaiOk
                        false -> "Sin conexión con la PC" to KaiWarn
                        null -> "Conectando…" to MaterialTheme.colorScheme.onSurfaceVariant
                    }
                    Text(label, color = color, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(end = 14.dp))
                },
            )
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(vm.tab == Tab.Chat, { vm.tab = Tab.Chat }, { Icon(Icons.AutoMirrored.Filled.Chat, null) }, label = { Text("Chat") })
                NavigationBarItem(vm.tab == Tab.Tasks, { vm.tab = Tab.Tasks; vm.refreshTasks() }, {
                    BadgedBox(badge = { if (waiting > 0) Badge { Text("$waiting") } }) { Icon(Icons.Filled.Checklist, null) }
                }, label = { Text("Tareas") })
                NavigationBarItem(vm.tab == Tab.History, { vm.tab = Tab.History; vm.refreshConversations() }, { Icon(Icons.Filled.History, null) }, label = { Text("Historial") })
                NavigationBarItem(vm.tab == Tab.Settings, { vm.tab = Tab.Settings }, { Icon(Icons.Filled.Settings, null) }, label = { Text("Ajustes") })
            }
        },
    ) { p ->
        val m = Modifier.padding(p)
        when (vm.tab) {
            Tab.Chat -> ChatScreen(vm, m)
            Tab.Tasks -> TasksScreen(vm, m)
            Tab.History -> HistoryScreen(vm, m)
            Tab.Settings -> SettingsScreen(vm, m)
        }
    }
}
