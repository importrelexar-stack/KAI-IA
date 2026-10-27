package ai.kai.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Parser incremental de Server-Sent Events: se le pasan líneas y devuelve el evento al cerrar cada bloque. */
class SseParser {
    private val data = StringBuilder()

    /** Devuelve el contenido `data` acumulado cuando llega la línea vacía que cierra el evento. */
    fun feed(line: String): String? {
        if (line.isEmpty()) {
            if (data.isEmpty()) return null
            val out = data.toString()
            data.setLength(0)
            return out
        }
        if (line.startsWith(":")) return null // comentario / keep-alive
        if (line.startsWith("data:")) {
            if (data.isNotEmpty()) data.append('\n')
            data.append(line.removePrefix("data:").removePrefix(" "))
        }
        return null
    }

    fun finish(): String? = if (data.isEmpty()) null else data.toString().also { data.setLength(0) }
}

/** Convierte el JSON de un evento de KAI en [ChatEvent]; los tipos desconocidos se ignoran (null). */
fun parseChatEvent(raw: String): ChatEvent? {
    val obj: JsonObject = KaiJson.parseToJsonElement(raw).jsonObject
    fun str(key: String) = obj[key]?.jsonPrimitive?.contentOrNull
    return when (str("type")) {
        "meta" -> ChatEvent.Meta(
            conversationId = str("conversation_id") ?: return null,
            userMessage = obj["user_message"]?.let { KaiJson.decodeFromJsonElement<Message>(it) },
            title = str("title"),
        )
        "delta" -> ChatEvent.Delta(str("text") ?: "")
        "tool" -> ChatEvent.Tool(
            ToolEvent(str("name") ?: "", str("summary") ?: "", obj["ok"]?.jsonPrimitive?.booleanOrNull ?: false, str("task_id")),
        )
        "done" -> ChatEvent.Done(
            conversationId = str("conversation_id") ?: return null,
            assistantMessage = KaiJson.decodeFromJsonElement(obj["assistant_message"] ?: return null),
        )
        "error" -> ChatEvent.Error(str("code") ?: "error", str("message") ?: "Error desconocido")
        else -> null
    }
}
