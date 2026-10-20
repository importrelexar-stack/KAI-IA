package ai.kai.android

import android.app.Application
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.kai.core.AttachmentOut
import ai.kai.core.AttachmentRef
import ai.kai.core.ChatEvent
import ai.kai.core.ConversationSummary
import ai.kai.core.KaiApiException
import ai.kai.core.KaiClient
import ai.kai.core.KaiTask
import ai.kai.core.Message
import ai.kai.core.Pairing
import ai.kai.core.PairingInfo
import ai.kai.core.PrivateNetwork
import ai.kai.core.ToolEvent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream

data class UiMessage(
    val id: String,
    val role: String,
    val content: String,
    val toolEvents: List<ToolEvent> = emptyList(),
    val attachments: List<AttachmentRef> = emptyList(),
    val pending: Boolean = false,
    val stopReason: String? = null,
) {
    companion object {
        fun from(m: Message) = UiMessage(m.id, m.role, m.content, m.toolEvents.orEmpty(), m.attachments.orEmpty(), stopReason = m.stopReason)
    }
}

enum class VoiceState { Idle, Listening, Transcribing, Thinking, Speaking }

enum class Tab { Chat, Tasks, History, Settings }

class KaiViewModel(app: Application) : AndroidViewModel(app) {
    private val store = SecureStore(app)
    private val recorder = VoiceRecorder()
    private val player = VoicePlayer(app)

    var session by mutableStateOf(store.load())
        private set
    var tab by mutableStateOf(Tab.Chat)
    var online by mutableStateOf<Boolean?>(null)
        private set
    var error by mutableStateOf<String?>(null)

    // Vinculación
    var pairingBusy by mutableStateOf(false)
        private set

    // Chat
    val messages = mutableStateListOf<UiMessage>()
    var conversationId by mutableStateOf<String?>(null)
        private set
    var busy by mutableStateOf(false)
        private set
    val attachments = mutableStateListOf<AttachmentOut>()
    var uploading by mutableStateOf(0)
        private set
    private var chatJob: Job? = null

    // Voz
    var voiceState by mutableStateOf(VoiceState.Idle)
        private set
    var speakReplies by mutableStateOf(true)
    private var voiceJob: Job? = null
    val micLevel get() = recorder.level

    // Tareas e historial
    var tasks by mutableStateOf<List<KaiTask>>(emptyList())
        private set
    var conversations by mutableStateOf<List<ConversationSummary>>(emptyList())
        private set

    private fun client(): KaiClient? = session?.let { KaiClient(it.baseUrl, it.token) }

    init {
        if (session != null) startPolling()
    }

    private fun handle(e: Throwable) {
        if (e is KaiApiException && e.status == 401) {
            error = "Este teléfono ya no está vinculado (se revocó en KAI). Volvé a vincularlo."
            unpair(keepError = true)
            return
        }
        if (e is KaiApiException && e.code == "offline") online = false
        error = e.message ?: "Error inesperado"
    }

    // ---------- Vinculación ----------

    fun pair(info: PairingInfo, deviceName: String) {
        if (pairingBusy) return
        pairingBusy = true
        error = null
        viewModelScope.launch {
            try {
                val url = KaiClient.firstReachable(info.urls)
                    ?: throw KaiApiException(0, "offline", "No se pudo llegar a KAI en ${info.urls.joinToString()}. " +
                        "Verificá que el teléfono esté en la misma Wi-Fi o en Tailscale y que el acceso remoto esté activado.")
                val res = KaiClient(url, null).pair(info.code, deviceName.ifBlank { Build.MODEL ?: "Android" })
                val s = Session(url, res.token, res.name, res.deviceId)
                store.save(s)
                session = s
                online = true
                (getApplication<Application>() as KaiApp).scheduleApprovalChecks()
                startPolling()
            } catch (e: Throwable) {
                handle(e)
            } finally {
                pairingBusy = false
            }
        }
    }

    fun pairManual(address: String, code: String, deviceName: String) {
        val url = PrivateNetwork.normalizeBaseUrl(address)
        when {
            url == null -> error = "Dirección inválida o fuera de tu red privada (ej.: 192.168.1.10 o mi-pc.tailnet.ts.net)."
            !Pairing.isValidCode(code) -> error = "El código tiene 8 caracteres (ej.: ABCD-EFGH)."
            else -> pair(PairingInfo(Pairing.normalizeCode(code), listOf(url)), deviceName)
        }
    }

    fun onQrScanned(payload: String?, deviceName: String) {
        val info = payload?.let { Pairing.parse(it) }
        when {
            payload == null -> Unit
            info == null -> error = "Ese QR no es de KAI. Abrí KAI en la PC → Dispositivos → Generar código."
            info.urls.isEmpty() -> error = "El QR no trae direcciones de red privada. Escribí la dirección a mano."
            else -> pair(info, deviceName)
        }
    }

    @OptIn(kotlinx.coroutines.DelicateCoroutinesApi::class)
    fun unpair(keepError: Boolean = false) {
        chatJob?.cancel(); voiceJob?.cancel(); player.stop()
        if (!keepError) client()?.let { c ->
            // Mejor esfuerzo: si la PC no responde, el token igual se borra acá (y se puede revocar desde la PC).
            kotlinx.coroutines.GlobalScope.launch { runCatching { c.unpairSelf() } }
        }
        store.clear()
        (getApplication<Application>() as KaiApp).cancelApprovalChecks()
        session = null
        messages.clear(); attachments.clear(); tasks = emptyList(); conversations = emptyList()
        conversationId = null
        if (!keepError) error = null
    }

    // ---------- Estado / tareas ----------

    private fun startPolling() {
        viewModelScope.launch {
            while (isActive && session != null) {
                refreshTasks(quiet = true)
                delay(20_000)
            }
        }
    }

    fun refreshTasks(quiet: Boolean = false) {
        val c = client() ?: return
        viewModelScope.launch {
            try {
                tasks = c.tasks()
                online = true
                ApprovalWorker.notifyNew(getApplication(), store, tasks)
            } catch (e: Throwable) {
                if (!quiet || (e is KaiApiException && e.status == 401)) handle(e) else if (e is KaiApiException && e.code == "offline") online = false
            }
        }
    }

    fun decide(task: KaiTask, approve: Boolean) {
        val c = client() ?: return
        viewModelScope.launch {
            try {
                val updated = c.decide(task.id, approve)
                tasks = tasks.map { if (it.id == updated.id) updated else it }
                if (conversationId != null) reloadConversation()
            } catch (e: Throwable) {
                handle(e)
            }
        }
    }

    fun refreshConversations() {
        val c = client() ?: return
        viewModelScope.launch {
            try {
                conversations = c.conversations()
                online = true
            } catch (e: Throwable) {
                handle(e)
            }
        }
    }

    fun openConversation(id: String) {
        conversationId = id
        tab = Tab.Chat
        reloadConversation()
    }

    private fun reloadConversation() {
        val c = client() ?: return
        val id = conversationId ?: return
        viewModelScope.launch {
            try {
                val detail = c.conversation(id)
                messages.clear()
                messages.addAll(detail.messages.filter { it.role == "user" || it.role == "assistant" }.map(UiMessage::from))
            } catch (e: Throwable) {
                handle(e)
            }
        }
    }

    fun newConversation() {
        if (busy) return
        conversationId = null
        messages.clear()
        attachments.clear()
        tab = Tab.Chat
    }

    // ---------- Adjuntos ----------

    fun attach(uri: Uri) {
        val c = client() ?: return
        if (attachments.size >= 5) { error = "Podés adjuntar hasta 5 archivos por mensaje."; return }
        uploading++
        viewModelScope.launch {
            try {
                val (name, mime, bytes) = readUri(uri)
                attachments.add(c.uploadAttachment(name, mime, bytes))
            } catch (e: Throwable) {
                handle(e)
            } finally {
                uploading--
            }
        }
    }

    fun removeAttachment(a: AttachmentOut) { attachments.remove(a) }

    /** Lee el archivo elegido; las fotos se achican (lado mayor 1568 px, JPEG) para no superar 5 MB. */
    private suspend fun readUri(uri: Uri): Triple<String, String, ByteArray> = withContext(Dispatchers.IO) {
        val cr = getApplication<Application>().contentResolver
        var name = "archivo"
        cr.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cur ->
            if (cur.moveToFirst()) name = cur.getString(0) ?: name
        }
        val mime = cr.getType(uri) ?: "application/octet-stream"
        val bytes = cr.openInputStream(uri)?.use { it.readBytes() } ?: throw IllegalStateException("No se pudo leer $name")
        if (mime.startsWith("image/") && bytes.size > 1_500_000) {
            val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@withContext Triple(name, mime, bytes)
            val scale = minOf(1f, 1568f / maxOf(bmp.width, bmp.height))
            val scaled = if (scale < 1f) Bitmap.createScaledBitmap(bmp, (bmp.width * scale).toInt(), (bmp.height * scale).toInt(), true) else bmp
            val out = ByteArrayOutputStream()
            scaled.compress(Bitmap.CompressFormat.JPEG, 85, out)
            return@withContext Triple(name.substringBeforeLast('.') + ".jpg", "image/jpeg", out.toByteArray())
        }
        Triple(name, mime, bytes)
    }

    // ---------- Chat ----------

    fun send(text: String, channel: String = "text", onReply: (suspend (String) -> Unit)? = null) {
        val c = client() ?: return
        val msg = text.trim()
        val sent = attachments.toList()
        if ((msg.isEmpty() && sent.isEmpty()) || busy || uploading > 0) return
        attachments.clear()
        error = null
        busy = true
        val tmp = "tmp-${System.currentTimeMillis()}"
        messages.add(UiMessage("$tmp-u", "user", msg, attachments = sent.map { it.ref() }, pending = true))
        messages.add(UiMessage("$tmp-a", "assistant", "", pending = true))
        fun update(id: String, f: (UiMessage) -> UiMessage) {
            val i = messages.indexOfFirst { it.id == id }
            if (i >= 0) messages[i] = f(messages[i])
        }
        chatJob = viewModelScope.launch {
            var reply: String? = null
            try {
                c.chat(msg, conversationId, channel, sent.map { it.id }).collect { ev ->
                    when (ev) {
                        is ChatEvent.Meta -> {
                            conversationId = ev.conversationId
                            ev.userMessage?.let { m -> update("$tmp-u") { UiMessage.from(m) } }
                        }
                        is ChatEvent.Delta -> update("$tmp-a") { it.copy(content = it.content + ev.text) }
                        is ChatEvent.Tool -> update("$tmp-a") { it.copy(toolEvents = it.toolEvents + ev.event) }
                        is ChatEvent.Done -> {
                            update("$tmp-a") { UiMessage.from(ev.assistantMessage) }
                            reply = ev.assistantMessage.content
                            if (ev.assistantMessage.toolEvents.orEmpty().any { it.taskId != null }) refreshTasks(quiet = true)
                        }
                        is ChatEvent.Error -> {
                            error = ev.message
                            messages.removeAll { it.id == "$tmp-a" }
                        }
                    }
                }
                online = true
            } catch (e: kotlinx.coroutines.CancellationException) {
                update("$tmp-a") { it.copy(pending = false, stopReason = "cancelled") }
                throw e
            } catch (e: Throwable) {
                messages.removeAll { it.id.startsWith(tmp) }
                attachments.addAll(sent)
                handle(e)
            } finally {
                busy = false
            }
            reply?.let { r -> onReply?.invoke(r) }
        }
    }

    fun stopReply() { chatJob?.cancel() }

    // ---------- Voz ----------

    /** Tocar el micrófono: empieza a escuchar; tocar de nuevo: termina. Si KAI está hablando, lo interrumpe. */
    fun toggleVoice() {
        when (voiceState) {
            VoiceState.Speaking -> { player.stop(); voiceState = VoiceState.Idle }
            VoiceState.Listening -> recorder.stop()
            VoiceState.Idle -> startVoice()
            else -> Unit
        }
    }

    private fun startVoice() {
        val c = client() ?: return
        if (busy) return
        error = null
        voiceJob = viewModelScope.launch {
            try {
                voiceState = VoiceState.Listening
                val wav = recorder.record()
                if (wav == null) { voiceState = VoiceState.Idle; error = "No te escuché. Probá de nuevo."; return@launch }
                voiceState = VoiceState.Transcribing
                val text = c.transcribe(wav).text.trim()
                if (text.isEmpty()) { voiceState = VoiceState.Idle; error = "No entendí el audio."; return@launch }
                voiceState = VoiceState.Thinking
                send(text, channel = "voice") { reply ->
                    if (speakReplies && reply.isNotBlank()) {
                        try {
                            val audio = c.synthesize(reply)
                            voiceState = VoiceState.Speaking
                            player.play(audio)
                        } catch (e: Throwable) {
                            if (e !is kotlinx.coroutines.CancellationException) handle(e)
                        }
                    }
                    voiceState = VoiceState.Idle
                }
                chatJob?.invokeOnCompletion { if (voiceState == VoiceState.Thinking) voiceState = VoiceState.Idle }
            } catch (e: Throwable) {
                voiceState = VoiceState.Idle
                if (e !is kotlinx.coroutines.CancellationException) handle(e)
            }
        }
    }

    override fun onCleared() {
        recorder.stop(); player.stop()
    }
}
