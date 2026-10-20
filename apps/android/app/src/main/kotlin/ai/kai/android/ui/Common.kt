package ai.kai.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Composable
fun KaiOrb(size: Dp, active: Boolean = false) {
    Box(
        Modifier.size(size).clip(CircleShape).background(
            Brush.radialGradient(listOf(Color(0xFFBFD6FF), KaiBlue, if (active) KaiBlue.copy(alpha = 0.6f) else KaiBg)),
        ),
    )
}

@Composable
fun ErrorBanner(text: String, onClose: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(KaiDanger.copy(alpha = 0.15f)).padding(start = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, color = KaiDanger, modifier = Modifier.weight(1f).padding(vertical = 10.dp))
        IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Cerrar", tint = KaiDanger) }
    }
}
