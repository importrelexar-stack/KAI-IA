package ai.kai.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

/** Modelos de la API de KAI Core (ver shared/openapi.json). Se ignoran los campos nuevos. */
val KaiJson = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

@Serializable
data class ToolEvent(val name: String, val summary: String, val ok: Boolean, @SerialName("task_id") val taskId: String? = null)

@Serializable
data class AttachmentRef(val id: String, val name: String, val kind: String, val size: Long = 0)

@Serializable
data class AttachmentOut(
    val id: String,
    val name: String,
    val kind: String,
    @SerialName("media_type") val mediaType: String,
    val size: Long,
    val chars: Int = 0,
) {
    fun ref() = AttachmentRef(id, name, kind, size)
}

@Serializable
data class Message(
    val id: String,
    val role: String,
    val content: String,
    val model: String? = null,
    @SerialName("stop_reason") val stopReason: String? = null,
    @SerialName("tool_events") val toolEvents: List<ToolEvent>? = null,
    val attachments: List<AttachmentRef>? = null,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class ConversationSummary(
    val id: String,
    val title: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("message_count") val messageCount: Int = 0,
)

@Serializable
data class ConversationDetail(val id: String, val title: String, val messages: List<Message>)

@Serializable
data class KaiTask(
    val id: String,
    val title: String,
    val description: String = "",
    val status: String,
    val priority: Int = 2,
    @SerialName("requires_approval") val requiresApproval: Boolean = false,
    val result: String? = null,
    val error: String? = null,
    @SerialName("created_by") val createdBy: String = "user",
    val action: JsonObject? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
) {
    val awaitingApproval get() = status == "awaiting_approval"
}

@Serializable
data class PairResult(val token: String, @SerialName("device_id") val deviceId: String, val name: String)

@Serializable
data class DeviceInfo(val id: String, val name: String, val platform: String)

@Serializable
data class Transcript(val text: String, val language: String = "", @SerialName("duration_seconds") val durationSeconds: Double = 0.0)

@Serializable
data class Health(val status: String, val version: String = "")

/** Eventos del chat en streaming (SSE). */
sealed interface ChatEvent {
    data class Meta(val conversationId: String, val userMessage: Message?, val title: String?) : ChatEvent
    data class Delta(val text: String) : ChatEvent
    data class Tool(val event: ToolEvent) : ChatEvent
    data class Done(val conversationId: String, val assistantMessage: Message) : ChatEvent
    data class Error(val code: String, val message: String) : ChatEvent
}

class KaiApiException(val status: Int, val code: String, message: String) : Exception(message)
