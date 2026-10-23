package ai.kai.android.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val KaiBlue = Color(0xFF2F7BFF)
val KaiBg = Color(0xFF05070B)
val KaiPanel = Color(0xFF10141C)
val KaiMuted = Color(0xFF8A94A6)
val KaiDanger = Color(0xFFFF5C5C)
val KaiWarn = Color(0xFFF5B83D)
val KaiOk = Color(0xFF3DDC97)

@Composable
fun KaiTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = KaiBlue,
            onPrimary = Color.White,
            background = KaiBg,
            surface = KaiBg,
            surfaceVariant = KaiPanel,
            surfaceContainer = KaiPanel,
            onSurface = Color(0xFFE8ECF3),
            onSurfaceVariant = KaiMuted,
            error = KaiDanger,
        ),
        content = content,
    )
}
