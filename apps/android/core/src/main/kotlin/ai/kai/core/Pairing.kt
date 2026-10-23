package ai.kai.core

import java.net.URLDecoder

/** Contenido del QR que muestra KAI (Configuración → Dispositivos): kai://pair?c=CODE&u=url1,url2 */
data class PairingInfo(val code: String, val urls: List<String>)

object Pairing {
    private val codeChars = Regex("[^A-Z0-9]")

    fun normalizeCode(code: String): String = codeChars.replace(code.uppercase(), "")

    fun isValidCode(code: String): Boolean = normalizeCode(code).length == 8

    /** Devuelve null si el QR no es de KAI. Sólo conserva direcciones de red privada. */
    fun parse(payload: String): PairingInfo? {
        val text = payload.trim()
        if (!text.startsWith("kai://pair?")) return null
        val params = text.substringAfter('?').split('&').mapNotNull {
            val k = it.substringBefore('=', "")
            if (k.isEmpty()) null else k to URLDecoder.decode(it.substringAfter('='), "UTF-8")
        }.toMap()
        val code = params["c"]?.takeIf { isValidCode(it) } ?: return null
        val urls = params["u"].orEmpty().split(',').mapNotNull { PrivateNetwork.normalizeBaseUrl(it) }.distinct()
        return PairingInfo(normalizeCode(code), urls)
    }
}
