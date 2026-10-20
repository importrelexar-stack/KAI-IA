package ai.kai.android.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import ai.kai.android.KaiViewModel
import ai.kai.android.Tab
import ai.kai.android.UiMessage
import ai.kai.android.VoiceState
import ai.kai.core.AttachmentRef

private val ACCEPT = arrayOf("image/*", "application/pdf", "text/*", "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@Composable
fun ChatScreen(vm: KaiViewModel, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    var input by rememberSaveable { mutableStateOf("") }
    val list = rememberLazyListState()
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris -> uris.forEach(vm::attach) }
    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) vm.toggleVoice() else vm.error = "Sin permiso de micrófono no puedo escucharte."
    }
    LaunchedEffect(vm.messages.size, vm.messages.lastOrNull()?.content?.length) {
        if (vm.messages.isNotEmpty()) list.animateScrollToItem(vm.messages.size - 1)
    }

    Column(modifier.fillMaxSize().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (vm.conversationId == null) "Nueva conversación" else "Conversación", color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f))
            IconButton(onClick = vm::newConversation, enabled = !vm.busy) { Icon(Icons.Filled.Add, "Nueva conversación") }
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (vm.messages.isEmpty()) item {
                Column(Modifier.fillMaxWidth().padding(top = 60.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    KaiOrb(72.dp)
                    Text("¿En qué te ayudo?", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 16.dp))
                    Text("Escribí, tocá el micrófono o adjuntá un archivo.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            items(vm.messages, key = { it.id }) { m -> Bubble(m, onOpenTask = { vm.tab = Tab.Tasks; vm.refreshTasks() }) }
        }
        vm.error?.let { Box(Modifier.padding(horizontal = 12.dp)) { ErrorBanner(it) { vm.error = null } } }
        VoiceStatus(vm)
        if (vm.attachments.isNotEmpty() || vm.uploading > 0) {
            LazyRow(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(vm.attachments, key = { it.id }) { a ->
                    InputChip(selected = false, onClick = { vm.removeAttachment(a) }, label = { Text(a.name, maxLines = 1) },
                        leadingIcon = { AttachmentIcon(a.kind) }, trailingIcon = { Icon(Icons.Filled.Close, "Quitar", Modifier.size(16.dp)) })
                }
                if (vm.uploading > 0) item { CircularProgressIndicator(Modifier.size(24.dp).padding(4.dp)) }
            }
        }
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.Bottom) {
            IconButton(onClick = { pick.launch(ACCEPT) }, enabled = !vm.busy && vm.attachments.size < 5) {
                Icon(Icons.Filled.AttachFile, "Adjuntar archivo")
            }
            OutlinedTextField(input, { input = it }, placeholder = { Text("Escribile a KAI…") }, maxLines = 5,
                modifier = Modifier.weight(1f))
            val voiceActive = vm.voiceState != VoiceState.Idle
            FilledIconButton(
                onClick = {
                    if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) vm.toggleVoice()
                    else micPermission.launch(Manifest.permission.RECORD_AUDIO)
                },
                enabled = !vm.busy || vm.voiceState == VoiceState.Speaking,
                colors = if (voiceActive) IconButtonDefaults.filledIconButtonColors(containerColor = KaiDanger) else IconButtonDefaults.filledIconButtonColors(),
                modifier = Modifier.padding(start = 6.dp),
            ) { Icon(if (vm.voiceState == VoiceState.Speaking) Icons.Filled.Stop else Icons.Filled.Mic, "Hablar con KAI") }
            if (vm.busy && vm.voiceState == VoiceState.Idle) {
                FilledIconButton(onClick = vm::stopReply, colors = IconButtonDefaults.filledIconButtonColors(containerColor = KaiDanger),
                    modifier = Modifier.padding(start = 6.dp)) { Icon(Icons.Filled.Stop, "Detener respuesta") }
            } else {
                FilledIconButton(
                    onClick = { vm.send(input); input = "" },
                    enabled = (input.isNotBlank() || vm.attachments.isNotEmpty()) && !vm.busy && vm.uploading == 0,
                    modifier = Modifier.padding(start = 6.dp),
                ) { Icon(Icons.AutoMirrored.Filled.Send, "Enviar") }
            }
        }
    }
}

@Composable
private fun VoiceStatus(vm: KaiViewModel) {
    val text = when (vm.voiceState) {
        VoiceState.Idle -> return
        VoiceState.Listening -> "Escuchando… (tocá el micrófono para terminar)"
        VoiceState.Transcribing -> "Transcribiendo…"
        VoiceState.Thinking -> "Pensando…"
        VoiceState.Speaking -> "KAI está hablando (tocá para interrumpir)"
    }
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(if (vm.voiceState == VoiceState.Speaking) Icons.Filled.VolumeUp else Icons.Filled.Mic, null, tint = KaiBlue)
        Text(text, color = KaiBlue, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
fun AttachmentIcon(kind: String) =
    Icon(if (kind == "image") Icons.Filled.Image else Icons.Filled.Description, null, Modifier.size(16.dp))

@Composable
private fun Bubble(m: UiMessage, onOpenTask: () -> Unit) {
    val isUser = m.role == "user"
    Box(Modifier.fillMaxWidth(), contentAlignment = if (isUser) Alignment.CenterEnd else Alignment.CenterStart) {
        Column(
            Modifier.widthIn(max = 320.dp).clip(RoundedCornerShape(16.dp))
                .background(if (isUser) KaiBlue.copy(alpha = 0.22f) else KaiPanel).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (m.attachments.isNotEmpty()) AttachmentList(m.attachments)
            m.toolEvents.forEach { t ->
                AssistChip(onClick = { if (t.taskId != null) onOpenTask() }, label = {
                    Text(if (t.taskId != null) "${t.summary} · ver" else t.summary, style = MaterialTheme.typography.labelSmall)
                })
            }
            when {
                m.content.isNotEmpty() && !isUser -> MarkdownText(m.content)
                m.content.isNotEmpty() -> SelectionContainer { Text(m.content) }
                m.pending && !isUser -> Text("…", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (m.stopReason == "cancelled") Text("Interrumpida", color = KaiWarn, style = MaterialTheme.typography.labelSmall)
            if (m.stopReason == "max_tokens") Text("Cortada por límite de tokens", color = KaiWarn, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun AttachmentList(items: List<AttachmentRef>) {
    items.forEach { a ->
        Row(verticalAlignment = Alignment.CenterVertically) {
            AttachmentIcon(a.kind)
            Text(a.name, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(start = 4.dp))
        }
    }
}
