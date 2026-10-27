package ai.kai.android

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import ai.kai.core.Wav
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume

/**
 * Graba 16 kHz mono. Se detiene sola tras ~1,2 s de silencio después de hablar (o a los 30 s),
 * o cuando se llama a [stop]. El umbral se calibra con el ruido de fondo de los primeros 300 ms.
 */
class VoiceRecorder {
    private val rate = 16_000
    @Volatile private var stopRequested = false
    @Volatile var level = 0.0
        private set

    fun stop() { stopRequested = true }

    /** Devuelve el WAV, o null si no se detectó voz. */
    @SuppressLint("MissingPermission") // el permiso se pide antes de llamar
    suspend fun record(maxSeconds: Int = 30, silenceMs: Int = 1200): ByteArray? = withContext(Dispatchers.IO) {
        stopRequested = false
        val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, rate / 5))
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            throw IllegalStateException("No se pudo abrir el micrófono.")
        }
        val out = Wav.Recorder()
        val chunk = ShortArray(rate / 20) // 50 ms
        var floor = 0.0
        var calibrated = 0
        var spoke = false
        var silentMs = 0
        try {
            rec.startRecording()
            while (!stopRequested && out.sampleCount < rate * maxSeconds) {
                ensureActive()
                val n = rec.read(chunk, 0, chunk.size)
                if (n <= 0) continue
                out.append(chunk, n)
                val rms = Wav.rms(chunk, n)
                level = rms
                if (calibrated < 6) { floor = maxOf(floor, rms); calibrated++; continue }
                val threshold = maxOf(floor * 2.5, 0.015)
                if (rms > threshold) { spoke = true; silentMs = 0 } else if (spoke) {
                    silentMs += n * 1000 / rate
                    if (silentMs >= silenceMs) break
                }
            }
        } finally {
            rec.stop(); rec.release(); level = 0.0
        }
        if (!spoke && !stopRequested) null else out.toWav(rate)
    }
}

/** Reproduce el WAV de la respuesta; se puede cortar (tocar el micrófono interrumpe a KAI). */
class VoicePlayer(private val context: Context) {
    private var player: MediaPlayer? = null
    private var finish: (() -> Unit)? = null

    suspend fun play(wav: ByteArray) {
        val file = File.createTempFile("kai-voz", ".wav", context.cacheDir)
        withContext(Dispatchers.IO) { file.writeBytes(wav) }
        try {
            suspendCancellableCoroutine { cont ->
                val mp = MediaPlayer()
                player = mp
                finish = { if (cont.isActive) cont.resume(Unit) }
                mp.setDataSource(file.absolutePath)
                mp.setOnCompletionListener { if (cont.isActive) cont.resume(Unit) }
                mp.setOnErrorListener { _, _, _ -> if (cont.isActive) cont.resume(Unit); true }
                mp.prepare()
                mp.start()
                cont.invokeOnCancellation { runCatching { mp.stop() } }
            }
        } finally {
            player?.release(); player = null; finish = null
            file.delete()
        }
    }

    fun stop() {
        runCatching { player?.stop() }
        finish?.invoke()
    }
}
