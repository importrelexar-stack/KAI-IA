package ai.kai.core

import java.net.URI

/**
 * La app sólo se conecta a KAI Core dentro de una red privada (igual que la regla del servidor):
 * loopback, LAN (10/8, 172.16/12, 192.168/16), Tailscale (100.64/10, *.ts.net), IPv6 ULA (fc00::/7) y *.local.
 * Nunca a direcciones públicas: así un QR malicioso no puede mandar el token a Internet.
 */
object PrivateNetwork {
    private val ipv4 = Regex("""^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$""")

    fun isPrivateHost(rawHost: String): Boolean {
        val host = rawHost.trim().trim('[', ']').lowercase()
        if (host.isEmpty()) return false
        ipv4.matchEntire(host)?.let { m ->
            val o = m.groupValues.drop(1).map { it.toInt() }
            if (o.any { it > 255 }) return false
            return o[0] == 10 || o[0] == 127 ||
                (o[0] == 172 && o[1] in 16..31) ||
                (o[0] == 192 && o[1] == 168) ||
                (o[0] == 100 && o[1] in 64..127)
        }
        if (host == "localhost" || host == "::1") return true
        if (host.contains(':')) { // IPv6 literal: sólo ULA fc00::/7
            val first = host.substringBefore(':').ifEmpty { return false }
            val v = first.toIntOrNull(16) ?: return false
            return first.length == 4 && ((v shr 8) and 0xFE) == 0xFC
        }
        return host.endsWith(".ts.net") || host.endsWith(".local")
    }

    /** Normaliza lo que escribe el usuario: "192.168.1.10" -> "http://192.168.1.10:8765". */
    fun normalizeBaseUrl(input: String, defaultPort: Int = 8765): String? {
        var s = input.trim().trimEnd('/')
        if (s.isEmpty()) return null
        if (!s.contains("://")) s = "http://$s"
        val uri = runCatching { URI(s) }.getOrNull() ?: return null
        if (uri.scheme !in setOf("http", "https") || uri.host == null) return null
        if (!isPrivateHost(uri.host)) return null
        val port = if (uri.port == -1) defaultPort else uri.port
        val host = if (uri.host.contains(':') && !uri.host.startsWith("[")) "[${uri.host}]" else uri.host
        return "${uri.scheme}://$host:$port"
    }
}
