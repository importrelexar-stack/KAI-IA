package ai.kai.core

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** WAV PCM 16 bits little-endian (lo que espera /voice/transcribe; 16 kHz mono es lo ideal para Whisper). */
object Wav {
    fun encode(pcm: ShortArray, sampleRate: Int = 16_000, channels: Int = 1): ByteArray {
        val dataBytes = pcm.size * 2
        val buf = ByteBuffer.allocate(44 + dataBytes).order(ByteOrder.LITTLE_ENDIAN)
        buf.put("RIFF".toByteArray()).putInt(36 + dataBytes).put("WAVE".toByteArray())
        buf.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(channels.toShort())
            .putInt(sampleRate).putInt(sampleRate * channels * 2).putShort((channels * 2).toShort()).putShort(16)
        buf.put("data".toByteArray()).putInt(dataBytes)
        pcm.forEach { buf.putShort(it) }
        return buf.array()
    }

    /** Duración en segundos de un PCM mono. */
    fun seconds(samples: Int, sampleRate: Int = 16_000) = samples.toDouble() / sampleRate

    /** Nivel RMS normalizado (0..1) para el medidor y la detección de silencio. */
    fun rms(pcm: ShortArray, length: Int = pcm.size): Double {
        if (length <= 0) return 0.0
        var sum = 0.0
        for (i in 0 until length) { val v = pcm[i] / 32768.0; sum += v * v }
        return kotlin.math.sqrt(sum / length)
    }

    class Recorder {
        private val out = ByteArrayOutputStream()
        private var samples = 0
        fun append(pcm: ShortArray, length: Int) {
            val b = ByteBuffer.allocate(length * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until length) b.putShort(pcm[i])
            out.write(b.array()); samples += length
        }
        val sampleCount get() = samples
        fun toWav(sampleRate: Int = 16_000): ByteArray {
            val raw = out.toByteArray()
            val pcm = ShortArray(raw.size / 2)
            ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().get(pcm)
            return encode(pcm, sampleRate)
        }
    }
}
