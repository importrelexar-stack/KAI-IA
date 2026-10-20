package ai.kai.android

import ai.kai.core.AttachmentRef
import ai.kai.core.Message
import ai.kai.core.ToolEvent
import org.junit.Assert.assertEquals
import org.junit.Test

class UiMessageTest {
    @Test fun mapsServerMessage() {
        val m = Message(
            id = "m1", role = "assistant", content = "Listo", stopReason = "end_turn",
            toolEvents = listOf(ToolEvent("files_move", "Pide autorización", true, "t1")),
            attachments = listOf(AttachmentRef("a1", "foto.jpg", "image", 10)), createdAt = "x",
        )
        val ui = UiMessage.from(m)
        assertEquals("t1", ui.toolEvents.single().taskId)
        assertEquals("foto.jpg", ui.attachments.single().name)
        assertEquals(false, ui.pending)
    }
}
