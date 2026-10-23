package ai.kai.android.ui

import android.os.Build
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import ai.kai.android.KaiViewModel
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import androidx.activity.compose.rememberLauncherForActivityResult

@Composable
fun PairScreen(vm: KaiViewModel, modifier: Modifier = Modifier) {
    var name by rememberSaveable { mutableStateOf(Build.MODEL ?: "Mi teléfono") }
    var address by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    val scan = rememberLauncherForActivityResult(ScanContract()) { res -> vm.onQrScanned(res.contents, name) }

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        KaiOrb(size = 64.dp)
        Text("Vincular con KAI", style = MaterialTheme.typography.headlineSmall)
        Text(
            "En la PC abrí KAI → Dispositivos, activá el acceso remoto y tocá «Generar código». " +
                "El teléfono tiene que estar en la misma Wi-Fi o en tu red Tailscale.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(name, { name = it.take(80) }, label = { Text("Nombre de este teléfono") }, singleLine = true,
            modifier = Modifier.fillMaxWidth())
        Button(
            onClick = {
                scan.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("Escaneá el QR de KAI")
                    .setBeepEnabled(false).setOrientationLocked(false))
            },
            enabled = !vm.pairingBusy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Filled.QrCodeScanner, contentDescription = null)
            Text("  Escanear QR")
        }
        Text("O a mano:", color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedTextField(address, { address = it.trim() }, label = { Text("Dirección de la PC") },
            placeholder = { Text("192.168.1.10 o mi-pc.tailnet.ts.net") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(code, { code = it.uppercase().take(9) }, label = { Text("Código (8 caracteres)") }, singleLine = true,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters), modifier = Modifier.fillMaxWidth())
        OutlinedButton(onClick = { vm.pairManual(address, code, name) }, enabled = !vm.pairingBusy, modifier = Modifier.fillMaxWidth()) {
            Text("Vincular")
        }
        if (vm.pairingBusy) CircularProgressIndicator()
        vm.error?.let { ErrorBanner(it) { vm.error = null } }
        Text(
            "Seguridad: KAI nunca se expone a Internet. El código sirve una sola vez y vence en 5 minutos; " +
                "el token queda cifrado en este teléfono y lo podés revocar desde la PC.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
