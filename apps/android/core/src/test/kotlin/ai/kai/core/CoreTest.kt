package ai.kai.core

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class NetworkTest {
    @Test fun privateHosts() {
        listOf("192.168.0.10", "10.1.2.3", "172.16.0.1", "172.31.255.1", "100.101.102.103", "fd7a:115c:a1e0::1",
            "[fd7a::1]", "mi-pc.tailnet.ts.net", "kai.local", "127.0.0.1", "localhost").forEach {
            assertTrue(it, PrivateNetwork.isPrivateHost(it))
        }
        listOf("8.8.8.8", "172.32.0.1", "100.128.0.1", "192.0.2.2", "2001:4860::8888", "evil.example.com", "999.1.1.1", "")
            .forEach { assertFalse(it, PrivateNetwork.isPrivateHost(it)) }
    }

    @Test fun normalizeBaseUrl() {
        assertEquals("http://192.168.1.10:8765", PrivateNetwork.normalizeBaseUrl("192.168.1.10"))
        assertEquals("http://192.168.1.10:9000", PrivateNetwork.normalizeBaseUrl(" http://192.168.1.10:9000/ "))
        assertEquals("http://mi-pc.tailnet.ts.net:8765", PrivateNetwork.normalizeBaseUrl("mi-pc.tailnet.ts.net"))
        assertNull(PrivateNetwork.normalizeBaseUrl("http://8.8.8.8:8765"))
        assertNull(PrivateNetwork.normalizeBaseUrl("ftp://192.168.1.10"))
        assertNull(PrivateNetwork.normalizeBaseUrl(""))
    }
}

class PairingTest {
    @Test fun parsesQrPayloadAndDropsPublicUrls() {
        val info = Pairing.parse("kai://pair?c=AB2C-D3EF&u=http://100.90.1.2:8765,http://8.8.8.8:8765,http://192.168.1.10:8765")!!
        assertEquals("AB2CD3EF", info.code)
        assertEquals(listOf("http://100.90.1.2:8765", "http://192.168.1.10:8765"), info.urls)
    }

    @Test fun rejectsForeignQr() {
        assertNull(Pairing.parse("https://example.com/?c=ABCD-EFGH"))
        assertNull(Pairing.parse("kai://pair?c=CORTO&u=http://192.168.1.2:8765"))
        assertEquals("ABCDEFGH", Pairing.normalizeCode("abcd efgh"))
        assertTrue(Pairing.isValidCode("abcd-efgh"))
    }
}

class SseAndWavTest {
    @Test fun parsesSseStream() {
        val p = SseParser()
        val lines = listOf(": ping", "event: delta", "data: {\"type\":\"delta\",\"text\":\"Hola\"}", "",
            "event: tool", "data: {\"type\":\"tool\",\"name\":\"memory_save\",\"summary\":\"Guardé\",\"ok\":true,\"task_id\":\"t1\"}", "",
            "data: {\"type\":\"futuro\"}", "")
        val events = lines.mapNotNull { p.feed(it) }.mapNotNull { parseChatEvent(it) }
        assertEquals(ChatEvent.Delta("Hola"), events[0])
        assertEquals(ChatEvent.Tool(ToolEvent("memory_save", "Guardé", true, "t1")), events[1])
        assertEquals(2, events.size)
    }

    @Test fun encodesWav() {
        val pcm = ShortArray(16_000) { (it % 100 * 100).toShort() }
        val wav = Wav.encode(pcm)
        assertEquals(44 + 32_000, wav.size)
        assertEquals("RIFF", String(wav, 0, 4)); assertEquals("WAVE", String(wav, 8, 4)); assertEquals("data", String(wav, 36, 4))
        val b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(16_000, b.getInt(24)); assertEquals(32_000, b.getInt(40)); assertEquals(pcm[7], b.getShort(44 + 14))
        val r = Wav.Recorder(); r.append(pcm, 100); r.append(pcm, 50)
        assertEquals(150, r.sampleCount); assertEquals(44 + 300, r.toWav().size)
        assertEquals(0.0, Wav.rms(ShortArray(10)), 0.0)
    }
}

class KaiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: KaiClient

    @Before fun setUp() {
        server = MockWebServer(); server.start()
        client = KaiClient(server.url("/").toString(), "kaid_token")
    }

    @After fun tearDown() = server.shutdown()

    @Test fun sendsTokenAndParsesTasks() = runBlocking {
        server.enqueue(MockResponse().setBody("""[{"id":"t1","title":"Mover","status":"awaiting_approval","created_at":"x","updated_at":"y","extra":1}]"""))
        val tasks = client.tasks("awaiting_approval")
        assertTrue(tasks.single().awaitingApproval)
        val req = server.takeRequest()
        assertEquals("Bearer kaid_token", req.getHeader("Authorization"))
        assertEquals("/api/v1/tasks?status=awaiting_approval", req.path)
    }

    @Test fun mapsApiErrors() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"error":{"code":"device_forbidden","message":"No"}}"""))
        try { client.me(); fail() } catch (e: KaiApiException) {
            assertEquals(403, e.status); assertEquals("device_forbidden", e.code); assertEquals("No", e.message)
        }
    }

    @Test fun streamsChat() = runBlocking {
        val sse = buildString {
            append("event: meta\ndata: {\"type\":\"meta\",\"conversation_id\":\"c1\",\"title\":\"Hola\"}\n\n")
            append("event: delta\ndata: {\"type\":\"delta\",\"text\":\"Ho\"}\n\n")
            append("event: delta\ndata: {\"type\":\"delta\",\"text\":\"la\"}\n\n")
            append("event: done\ndata: {\"type\":\"done\",\"conversation_id\":\"c1\",\"assistant_message\":{\"id\":\"m2\",\"role\":\"assistant\",\"content\":\"Hola\",\"created_at\":\"x\"}}\n\n")
        }
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(sse))
        val events = client.chat("hola", null, attachmentIds = listOf("a1")).toList()
        assertEquals("Hola", events.filterIsInstance<ChatEvent.Delta>().joinToString("") { it.text })
        assertEquals("Hola", (events.last() as ChatEvent.Done).assistantMessage.content)
        val body = server.takeRequest().body.readUtf8()
        assertTrue(body, body.contains("\"attachment_ids\":[\"a1\"]") && body.contains("\"stream\":true"))
    }

    @Test fun uploadsMultipart() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"id":"a1","name":"n.txt","kind":"document","media_type":"text/plain","size":4,"chars":4}"""))
        val att = client.uploadAttachment("n.txt", "text/plain", "hola".toByteArray())
        assertEquals("a1", att.id)
        val req = server.takeRequest()
        assertTrue(req.getHeader("Content-Type")!!.startsWith("multipart/form-data"))
        assertTrue(req.body.readUtf8().contains("filename=\"n.txt\""))
    }

    @Test fun routinesListAndRun() = runBlocking {
        server.enqueue(MockResponse().setBody("""[{"id":"r1","name":"Resumen","schedule_text":"todos los días a las 08:00","last_status":"ok","conversation_id":"c1","run_count":3}]"""))
        server.enqueue(MockResponse().setResponseCode(202).setBody("""{"status":"started"}"""))
        val r = client.routines().single()
        assertEquals("ok", r.lastStatus); assertEquals(3, r.runCount)
        client.runRoutine("r1")
        server.takeRequest()
        val run = server.takeRequest()
        assertEquals("POST", run.method); assertEquals("/api/v1/routines/r1/run", run.path)
    }

    @Test fun refusesPublicAddresses() {
        try { KaiClient("http://8.8.8.8:8765", "x"); fail() } catch (_: IllegalArgumentException) {}
    }

    @Test fun offlineIsReported() = runBlocking {
        val dead = KaiClient("http://127.0.0.1:1", null)
        try { dead.health(); fail() } catch (e: KaiApiException) { assertEquals("offline", e.code) }
    }
}
