package ai.kai.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.kai.core.Markdown

private fun annotate(spans: List<Markdown.Span>, codeBg: Color): AnnotatedString = buildAnnotatedString {
    for (s in spans) {
        val style = SpanStyle(
            fontWeight = if (s.bold) FontWeight.SemiBold else null,
            fontStyle = if (s.italic) FontStyle.Italic else null,
            fontFamily = if (s.code) FontFamily.Monospace else null,
            background = if (s.code) codeBg else Color.Unspecified,
        )
        withStyle(style) { append(s.text) }
    }
}

/** Respuesta de KAI con formato (títulos, listas, negrita, código). */
@Composable
fun MarkdownText(text: String, modifier: Modifier = Modifier) {
    val blocks = remember(text) { Markdown.parse(text) }
    val codeBg = Color.White.copy(alpha = 0.08f)
    SelectionContainer(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (b in blocks) {
                val body = annotate(b.spans, codeBg)
                when (b.kind) {
                    Markdown.Kind.Heading -> Text(body, fontWeight = FontWeight.SemiBold,
                        fontSize = when (b.level) { 1 -> 20.sp; 2 -> 18.sp; else -> 16.sp })
                    Markdown.Kind.Bullet, Markdown.Kind.Numbered -> Row(Modifier.padding(start = (b.level * 14).dp)) {
                        Text(b.marker, modifier = Modifier.width(22.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(body)
                    }
                    Markdown.Kind.Quote -> Text(body, fontStyle = FontStyle.Italic, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 8.dp))
                    Markdown.Kind.Code -> Text(body, fontFamily = FontFamily.Monospace, fontSize = 13.sp,
                        modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(codeBg)
                            .horizontalScroll(rememberScrollState()).padding(10.dp), softWrap = false)
                    Markdown.Kind.Paragraph -> Text(body)
                }
            }
        }
    }
}
