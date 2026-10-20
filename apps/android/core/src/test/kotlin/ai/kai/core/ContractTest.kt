package ai.kai.core

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * Prueba de contrato contra un KAI Core real (modo demostración). Se activa con KAI_TEST_URL,
 * por ejemplo http://127.0.0.1:8765 (el workflow de Android la levanta). Sin la variable, se omite.
 */
class ContractTest {
    private val base = System.getenv("KAI_TEST_URL").orEmpty()
    private val http = OkHttpClient()
    private val json = "application/json".toMediaType()

    private fun admin(method: String, path: String, body: String? = null): String {
        val req = Request.Builder().url("$base/api/v1$path").method(method, body?.toRequestBody(json)).build()
        http.newCall(req).execute().use { res ->
            val text = res.body!!.string()
            assertTrue("$method $path -> ${res.code}: $text", res.isSuccessful)
            return text
        }
    }

    @Test fun phoneFlowAgainstRealKai() = runBlocking {
        assumeTrue("KAI_TEST_URL no definida", base.isNotBlank())
        admin("PUT", "/devices/remote", """{"enabled":true}""")
        val pairing = KaiJson.parseToJsonElement(admin("POST", "/devices/pairing", "{}")).jsonObject
        val payload = pairing["payload"]!!.jsonPrimitive.content
        val info = Pairing.parse(payload.replace(Regex("u=[^&]*"), "u=$base"))!!

        val anon = KaiClient(base, null)
        assertEquals("ok", anon.health().status)
        val paired = anon.pair(info.code, "Contrato")
        assertTrue(paired.token.startsWith("kaid_"))

        val c = KaiClient(base, paired.token)
        val att = c.uploadAttachment("nota.txt", "text/plain", "Comprar tornillos".toByteArray())
        assertEquals("document", att.kind)
        val events = c.chat("Hola desde el teléfono", null, attachmentIds = listOf(att.id)).toList()
        val meta = events.first() as ChatEvent.Meta
        val done = events.last() as ChatEvent.Done
        assertTrue(events.any { it is ChatEvent.Delta })
        assertTrue(done.assistantMessage.content.isNotBlank())

        val detail = c.conversation(meta.conversationId)
        assertEquals(listOf("user", "assistant"), detail.messages.map { it.role })
        assertEquals("nota.txt", detail.messages.first().attachments!!.single().name)
        assertTrue(c.conversations().any { it.id == meta.conversationId })
        c.tasks()
        val devices = admin("GET", "/devices")
        assertTrue(devices.contains("\"Contrato\""))
    }
}
