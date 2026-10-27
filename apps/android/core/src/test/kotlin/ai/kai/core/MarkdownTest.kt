package ai.kai.core

import ai.kai.core.Markdown.Kind
import ai.kai.core.Markdown.Span
import org.junit.Assert.assertEquals
import org.junit.Test

class MarkdownTest {
    @Test fun blocks() {
        val md = """
            # Resumen
            Tenés **2 tareas** y un `script`.
            Segunda línea.

            - Pagar *luz*
              - sub
            1. Primero
            > Ojo
            ```
            código **sin formato**
            ```
        """.trimIndent()
        val b = Markdown.parse(md)
        assertEquals(listOf(Kind.Heading, Kind.Paragraph, Kind.Bullet, Kind.Bullet, Kind.Numbered, Kind.Quote, Kind.Code), b.map { it.kind })
        assertEquals(1, b[0].level)
        assertEquals(listOf(Span("Tenés "), Span("2 tareas", bold = true), Span(" y un "), Span("script", code = true),
            Span(".\nSegunda línea.")), b[1].spans)
        assertEquals(listOf(Span("Pagar "), Span("luz", italic = true)), b[2].spans)
        assertEquals(1, b[3].level)
        assertEquals("1.", b[4].marker)
        assertEquals("código **sin formato**", b[6].spans.single().text)
    }

    @Test fun plainTextAndEdgeCases() {
        assertEquals(listOf(Span("2 * 3 = 6 y snake_case_name")), Markdown.inlineSpans("2 * 3 = 6 y snake_case_name"))
        assertEquals(listOf(Kind.Code), Markdown.parse("```\nsin cierre").map { it.kind })
        assertEquals(emptyList<Markdown.Block>(), Markdown.parse("\n\n"))
        assertEquals(listOf(Span("es "), Span("muy", italic = true), Span(" claro")), Markdown.inlineSpans("es _muy_ claro"))
        assertEquals(listOf(Span("archivo "), Span("__init__.py", code = true)), Markdown.inlineSpans("archivo `__init__.py`"))
    }
}
