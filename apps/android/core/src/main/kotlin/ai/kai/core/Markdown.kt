package ai.kai.core

/**
 * Markdown mínimo para mostrar respuestas en el teléfono: títulos, listas, citas, bloques de código,
 * negrita, cursiva y código en línea. Lo que no reconoce queda como texto (nunca se pierde contenido).
 */
object Markdown {
    enum class Kind { Paragraph, Heading, Bullet, Numbered, Quote, Code }

    data class Span(val text: String, val bold: Boolean = false, val italic: Boolean = false, val code: Boolean = false)

    data class Block(val kind: Kind, val spans: List<Span>, val level: Int = 0, val marker: String = "")

    private val heading = Regex("""^(#{1,6})\s+(.*)$""")
    private val bullet = Regex("""^(\s*)[-*+]\s+(.*)$""")
    private val numbered = Regex("""^(\s*)(\d{1,3})[.)]\s+(.*)$""")
    // `_…_` y `__…__` sólo cuentan si no están pegados a letras o números (snake_case queda como texto).
    private val inline = Regex(
        """(`[^`]+`)|(\*\*[^*]+\*\*|(?<![\p{L}\p{N}])__[^_]+__(?![\p{L}\p{N}]))|""" +
            """(\*[^*\s][^*]*\*|(?<![\p{L}\p{N}])_[^_\s][^_]*_(?![\p{L}\p{N}]))""",
    )

    fun parse(text: String): List<Block> {
        val out = mutableListOf<Block>()
        val para = StringBuilder()
        var code: StringBuilder? = null
        fun flush() {
            if (para.isNotBlank()) out += Block(Kind.Paragraph, inlineSpans(para.toString().trim()))
            para.setLength(0)
        }
        for (raw in text.replace("\r\n", "\n").split('\n')) {
            val line = raw.trimEnd()
            if (line.trimStart().startsWith("```")) {
                if (code == null) { flush(); code = StringBuilder() } else {
                    out += Block(Kind.Code, listOf(Span(code.toString().trimEnd('\n'), code = true)))
                    code = null
                }
                continue
            }
            if (code != null) { code.append(raw).append('\n'); continue }
            if (line.isBlank()) { flush(); continue }
            heading.matchEntire(line)?.let { m ->
                flush(); out += Block(Kind.Heading, inlineSpans(m.groupValues[2]), level = m.groupValues[1].length); return@let
            } ?: bullet.matchEntire(line)?.let { m ->
                flush(); out += Block(Kind.Bullet, inlineSpans(m.groupValues[2]), level = m.groupValues[1].length / 2, marker = "•")
            } ?: numbered.matchEntire(line)?.let { m ->
                flush(); out += Block(Kind.Numbered, inlineSpans(m.groupValues[3]), level = m.groupValues[1].length / 2,
                    marker = "${m.groupValues[2]}.")
            } ?: if (line.startsWith(">")) {
                flush(); out += Block(Kind.Quote, inlineSpans(line.removePrefix(">").trim()))
            } else {
                if (para.isNotEmpty()) para.append('\n')
                para.append(line)
            }
        }
        code?.let { out += Block(Kind.Code, listOf(Span(it.toString().trimEnd('\n'), code = true))) } // sin cierre
        flush()
        return out
    }

    fun inlineSpans(text: String): List<Span> {
        val spans = mutableListOf<Span>()
        var last = 0
        for (m in inline.findAll(text)) {
            if (m.range.first > last) spans += Span(text.substring(last, m.range.first))
            val v = m.value
            spans += when {
                m.groups[1] != null -> Span(v.substring(1, v.length - 1), code = true)
                m.groups[2] != null -> Span(v.substring(2, v.length - 2), bold = true)
                else -> Span(v.substring(1, v.length - 1), italic = true)
            }
            last = m.range.last + 1
        }
        if (last < text.length) spans += Span(text.substring(last))
        return spans
    }
}
