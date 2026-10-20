package ai.kai.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Cliente de KAI Core para el teléfono. Todas las llamadas llevan el token del dispositivo
 * (Authorization: Bearer kaid_…). Sólo acepta URLs de red privada.
 */
class KaiClient(
    baseUrl: String,
    private val token: String?,
    http: OkHttpClient = defaultHttp(),
) {
    val baseUrl: String = PrivateNetwork.normalizeBaseUrl(baseUrl)
        ?: throw IllegalArgumentException("Dirección fuera de la red privada: $baseUrl")

    private val http = http
    private val streamHttp = http.newBuilder().readTimeout(10, TimeUnit.MINUTES).build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    companion object {
        const val API = "/api/v1"

        fun defaultHttp(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS) // transcribir/sintetizar puede tardar en CPU
            .writeTimeout(60, TimeUnit.SECONDS)
            .build()

        /** Prueba las direcciones del QR en orden (Tailscale primero) y devuelve la primera que responde. */
        suspend fun firstReachable(urls: List<String>, http: OkHttpClient = defaultHttp()): String? {
            val quick = http.newBuilder().connectTimeout(3, TimeUnit.SECONDS).readTimeout(5, TimeUnit.SECONDS).build()
            for (u in urls) {
                val ok = runCatching { KaiClient(u, null, quick).health() }.isSuccess
                if (ok) return PrivateNetwork.normalizeBaseUrl(u)
            }
            return null
        }
    }

    @Serializable
    private data class PairBody(val code: String, val name: String, val platform: String)

    @Serializable
    private data class ChatBody(
        val message: String,
        @SerialName("conversation_id") val conversationId: String?,
        val stream: Boolean,
        val channel: String,
        @SerialName("attachment_ids") val attachmentIds: List<String>,
    )

    @Serializable
    private data class ApprovalBody(val approve: Boolean, val note: String? = null)

    @Serializable
    private data class SynthBody(val text: String)

    private fun url(path: String) = (baseUrl + API + path).toHttpUrl()

    private fun request(path: String) = Request.Builder().url(url(path)).apply {
        if (token != null) header("Authorization", "Bearer $token")
    }

    private fun check(res: Response): Response {
        if (res.isSuccessful) return res
        val body = res.body?.string().orEmpty()
        res.close()
        val err = runCatching { KaiJson.parseToJsonElement(body).jsonObject["error"]?.jsonObject }.getOrNull()
        throw KaiApiException(
            res.code,
            err?.get("code")?.jsonPrimitive?.contentOrNull ?: "http_${res.code}",
            err?.get("message")?.jsonPrimitive?.contentOrNull ?: "KAI respondió ${res.code}.",
        )
    }

    private suspend fun call(req: Request, client: OkHttpClient = http): String = withContext(Dispatchers.IO) {
        try {
            check(client.newCall(req).execute()).use { it.body?.string().orEmpty() }
        } catch (e: IOException) {
            throw KaiApiException(0, "offline", "No se pudo conectar con KAI. ¿La PC está encendida y en la misma red?")
        }
    }

    private suspend inline fun <reified T> get(path: String): T = KaiJson.decodeFromString(call(request(path).get().build()))

    private suspend inline fun <reified B, reified T> post(path: String, body: B): T =
        KaiJson.decodeFromString(call(request(path).post(KaiJson.encodeToString(body).toRequestBody(jsonType)).build()))

    suspend fun health(): Health = get("/health")

    suspend fun pair(code: String, name: String, platform: String = "android"): PairResult =
        post("/devices/pair", PairBody(Pairing.normalizeCode(code), name, platform))

    suspend fun me(): DeviceInfo = get("/devices/me")

    /** Revoca el token de este teléfono en KAI (desvincular). */
    suspend fun unpairSelf() {
        call(request("/devices/me").delete().build())
    }

    suspend fun conversations(limit: Int = 50): List<ConversationSummary> = get("/conversations?limit=$limit")

    suspend fun conversation(id: String): ConversationDetail = get("/conversations/$id")

    suspend fun tasks(status: String? = null): List<KaiTask> = get(if (status == null) "/tasks" else "/tasks?status=$status")

    suspend fun decide(taskId: String, approve: Boolean, note: String? = null): KaiTask =
        post("/tasks/$taskId/approval", ApprovalBody(approve, note))

    suspend fun routines(): List<Routine> = get("/routines")

    /** Ejecuta la rutina ahora (en segundo plano en la PC). */
    suspend fun runRoutine(id: String) {
        call(request("/routines/$id/run").post(ByteArray(0).toRequestBody(null)).build())
    }

    suspend fun uploadAttachment(name: String, mimeType: String, bytes: ByteArray): AttachmentOut {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", name, bytes.toRequestBody(mimeType.toMediaType()))
            .build()
        return KaiJson.decodeFromString(call(request("/chat/attachments").post(body).build()))
    }

    suspend fun transcribe(wav: ByteArray, language: String? = null): Transcript {
        val form = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("audio", "voz.wav", wav.toRequestBody("audio/wav".toMediaType()))
        if (language != null) form.addFormDataPart("language", language)
        return KaiJson.decodeFromString(call(request("/voice/transcribe").post(form.build()).build()))
    }

    /** Devuelve el audio WAV de la respuesta (voz local de KAI). */
    suspend fun synthesize(text: String): ByteArray = withContext(Dispatchers.IO) {
        val req = request("/voice/synthesize").post(KaiJson.encodeToString(SynthBody(text)).toRequestBody(jsonType)).build()
        try {
            check(http.newCall(req).execute()).use { it.body?.bytes() ?: ByteArray(0) }
        } catch (e: IOException) {
            throw KaiApiException(0, "offline", "No se pudo conectar con KAI.")
        }
    }

    /** Chat en streaming. Cancelar la corrutina corta la conexión (KAI deja de generar). */
    fun chat(
        message: String,
        conversationId: String?,
        channel: String = "text",
        attachmentIds: List<String> = emptyList(),
    ): Flow<ChatEvent> = flow {
        val body = KaiJson.encodeToString(ChatBody(message, conversationId, true, channel, attachmentIds))
        val req = request("/chat").header("Accept", "text/event-stream").post(body.toRequestBody(jsonType)).build()
        val call = streamHttp.newCall(req)
        val res = try {
            call.execute()
        } catch (e: IOException) {
            throw KaiApiException(0, "offline", "No se pudo conectar con KAI.")
        }
        try {
            check(res)
            val source = res.body!!.source()
            val parser = SseParser()
            while (true) {
                val line = source.readUtf8Line() ?: break
                parser.feed(line)?.let { raw -> parseChatEvent(raw)?.let { emit(it) } }
            }
            parser.finish()?.let { raw -> parseChatEvent(raw)?.let { emit(it) } }
        } finally {
            res.close()
            call.cancel()
        }
    }.flowOn(Dispatchers.IO)
}
