package ai.kai.android.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import ai.kai.android.KaiViewModel
import ai.kai.core.KaiTask
import kotlinx.serialization.json.JsonPrimitive

private val STATUS = mapOf(
    "awaiting_approval" to "Espera tu autorización", "pending" to "Pendiente", "running" to "En curso",
    "completed" to "Completada", "failed" to "Falló", "cancelled" to "Cancelada",
)

@Composable
fun TasksScreen(vm: KaiViewModel, modifier: Modifier = Modifier) {
    LaunchedEffect(Unit) { vm.refreshTasks() }
    val sorted = vm.tasks.sortedByDescending { it.awaitingApproval }
    var confirm by remember { mutableStateOf<Pair<KaiTask, Boolean>?>(null) }
    LazyColumn(modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        vm.error?.let { item { ErrorBanner(it) { vm.error = null } } }
        if (sorted.isEmpty()) item { Text("No hay tareas.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        items(sorted, key = { it.id }) { t ->
            Card(colors = CardDefaults.cardColors(containerColor = KaiPanel)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(t.title, style = MaterialTheme.typography.titleSmall)
                    Text(STATUS[t.status] ?: t.status, color = when (t.status) {
                        "awaiting_approval" -> KaiWarn; "completed" -> KaiOk; "failed" -> KaiDanger; else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }, style = MaterialTheme.typography.labelMedium)
                    if (t.description.isNotBlank()) Text(t.description, style = MaterialTheme.typography.bodySmall)
                    ActionDetail(t)
                    t.result?.takeIf { it.isNotBlank() }?.let { Text(it.take(500), style = MaterialTheme.typography.bodySmall) }
                    t.error?.takeIf { it.isNotBlank() }?.let { Text(it, color = KaiDanger, style = MaterialTheme.typography.bodySmall) }
                    if (t.awaitingApproval) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { confirm = t to true }) { Text("Autorizar") }
                            OutlinedButton(onClick = { confirm = t to false }) { Text("Rechazar") }
                        }
                    }
                }
            }
        }
    }
    confirm?.let { (t, approve) ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(if (approve) "¿Autorizar esta acción?" else "¿Rechazar esta acción?") },
            text = { Text(t.title + if (approve) "\n\nKAI la va a ejecutar en tu PC." else "") },
            confirmButton = {
                Button(onClick = { vm.decide(t, approve); confirm = null },
                    colors = if (approve) ButtonDefaults.buttonColors() else ButtonDefaults.buttonColors(containerColor = KaiDanger)) {
                    Text(if (approve) "Autorizar" else "Rechazar")
                }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancelar") } },
        )
    }
}

/** Muestra exactamente qué va a hacer la acción (herramienta y argumentos) antes de autorizarla. */
@Composable
private fun ActionDetail(t: KaiTask) {
    val action = t.action ?: return
    val tool = (action["tool"] as? JsonPrimitive)?.content ?: return
    val args = action["args"]?.toString().orEmpty()
    Text("Acción: $tool\n${args.take(400)}", fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun HistoryScreen(vm: KaiViewModel, modifier: Modifier = Modifier) {
    LaunchedEffect(Unit) { vm.refreshConversations() }
    LazyColumn(modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp)) {
        vm.error?.let { item { ErrorBanner(it) { vm.error = null } } }
        if (vm.conversations.isEmpty()) item { Text("Todavía no hay conversaciones.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        items(vm.conversations, key = { it.id }) { c ->
            Column(Modifier.fillMaxWidth().clickable { vm.openConversation(c.id) }.padding(vertical = 12.dp)) {
                Text(c.title, style = MaterialTheme.typography.bodyLarge)
                Text("${c.messageCount} mensajes · ${c.updatedAt.take(16).replace('T', ' ')} UTC",
                    color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
            }
            HorizontalDivider()
        }
    }
}

@Composable
fun SettingsScreen(vm: KaiViewModel, modifier: Modifier = Modifier) {
    val s = vm.session ?: return
    var confirmUnpair by remember { mutableStateOf(false) }
    Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Este teléfono", style = MaterialTheme.typography.titleMedium)
        Text("${s.deviceName}\nConectado a ${s.baseUrl}", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Leer las respuestas en voz alta (modo voz)", modifier = Modifier.weight(1f))
            Switch(checked = vm.speakReplies, onCheckedChange = { vm.speakReplies = it })
        }
        Text(
            "La voz se transcribe y se genera en tu PC (motores locales de KAI): el audio no sale de tu red. " +
                "Las notificaciones de autorizaciones se revisan cada 15 minutos y al abrir la app.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedButton(onClick = { confirmUnpair = true }, colors = ButtonDefaults.outlinedButtonColors(contentColor = KaiDanger)) {
            Text("Desvincular este teléfono")
        }
        Text("Para revocar el acceso desde la PC: KAI → Dispositivos → Revocar.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (confirmUnpair) AlertDialog(
        onDismissRequest = { confirmUnpair = false },
        title = { Text("¿Desvincular?") },
        text = { Text("Se borra el token de este teléfono. Para volver a usar KAI vas a necesitar un código nuevo. " +
            "(Revocalo también desde la PC para invalidarlo del todo.)") },
        confirmButton = { Button(onClick = { vm.unpair(); confirmUnpair = false }) { Text("Desvincular") } },
        dismissButton = { TextButton(onClick = { confirmUnpair = false }) { Text("Cancelar") } },
    )
}
