package ai.kai.android

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Sesión con KAI Core: dirección de la PC y token del dispositivo. */
data class Session(val baseUrl: String, val token: String, val deviceName: String, val deviceId: String)

/**
 * Guarda el token cifrado con una clave AES-GCM del Android Keystore (no exportable).
 * Si la clave se pierde (restauración, cambio de dispositivo), la sesión se descarta y hay que volver a vincular.
 */
class SecureStore(context: Context) {
    private val prefs = context.getSharedPreferences("kai_session", Context.MODE_PRIVATE)
    private val alias = "kai_device_token"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }

    fun save(s: Session) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val ct = cipher.doFinal(s.token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString("base_url", s.baseUrl)
            .putString("device_name", s.deviceName)
            .putString("device_id", s.deviceId)
            .putString("token_iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("token_ct", Base64.encodeToString(ct, Base64.NO_WRAP))
            .apply()
    }

    fun load(): Session? {
        val url = prefs.getString("base_url", null) ?: return null
        val iv = prefs.getString("token_iv", null) ?: return null
        val ct = prefs.getString("token_ct", null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            val token = String(cipher.doFinal(Base64.decode(ct, Base64.NO_WRAP)), Charsets.UTF_8)
            Session(url, token, prefs.getString("device_name", "") ?: "", prefs.getString("device_id", "") ?: "")
        } catch (e: Exception) {
            clear()
            null
        }
    }

    fun updateUrl(url: String) = prefs.edit().putString("base_url", url).apply()

    fun clear() = prefs.edit().clear().apply()

    /** IDs de tareas ya notificadas (para no repetir la notificación). */
    var notifiedTasks: Set<String>
        get() = prefs.getStringSet("notified_tasks", emptySet()) ?: emptySet()
        set(v) = prefs.edit().putStringSet("notified_tasks", v.toList().takeLast(200).toSet()).apply()
}
