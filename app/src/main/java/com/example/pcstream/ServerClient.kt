package com.example.pcstream

import android.net.Uri
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** One row returned by the PC server's /api/list. */
data class Entry(
    val name: String,
    val path: String,
    val isDir: Boolean,
    val size: Long,
    val isMedia: Boolean,
    val mime: String
)

/** A monitor the PC can share. Index -1 means "all screens at once". */
data class Monitor(val index: Int, val label: String)

class ServerException(message: String) : IOException(message)

/**
 * Talks to serve.py. Every call blocks, so callers run it off the main thread.
 */
class ServerClient(baseUrl: String, private val token: String) {

    /** Normalised base, never with a trailing slash. */
    val base: String = baseUrl.trim()
        .let { if (it.startsWith("http://") || it.startsWith("https://")) it else "http://$it" }
        .trimEnd('/')

    /** Returns the PC's hostname if the server answers. */
    fun ping(): String {
        val json = getJson("$base/api/ping")
        return json.optString("name", "PC")
    }

    fun list(path: String): List<Entry> {
        val url = Uri.parse("$base/api/list").buildUpon()
            .appendQueryParameter("path", path)
            .build().toString()
        val entries = getJson(url).getJSONArray("entries")
        return (0 until entries.length()).map { i ->
            val o = entries.getJSONObject(i)
            Entry(
                name = o.getString("name"),
                path = o.getString("path"),
                isDir = o.getBoolean("dir"),
                size = o.optLong("size", 0L),
                isMedia = o.optBoolean("media", false),
                mime = o.optString("mime", "application/octet-stream")
            )
        }
    }

    /** Monitors available for screen sharing. Empty if the PC has none. */
    fun screens(): List<Monitor> {
        val json = getJson("$base/api/screens")
        val arr = json.getJSONArray("monitors")
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            Monitor(o.getInt("index"), o.getString("label"))
        }
    }

    /** True when the PC reports ffmpeg present and screen sharing enabled. */
    fun screenSupported(): Boolean = getJson("$base/api/ping").optBoolean("screen", false)

    /** Whether the PC found a desktop-audio device; null when it did not. */
    fun screenAudioDevice(): String? =
        getJson("$base/api/screens").optString("audio", "").ifEmpty { null }

    /** Live MPEG-TS URL for one monitor. */
    fun screenUrl(monitor: Int, height: Int = 720, fps: Int = 30): String {
        val url = "$base/screen.ts?monitor=$monitor&height=$height&fps=$fps"
        return if (token.isEmpty()) url else "$url&token=${Uri.encode(token)}"
    }

    /**
     * Streaming URL for a file. The token rides in the query string so the
     * player does not need custom request headers.
     */
    fun mediaUrl(path: String): String {
        val encoded = path.split('/').joinToString("/") { Uri.encode(it) }
        val url = "$base/media/$encoded"
        return if (token.isEmpty()) url else "$url?token=${Uri.encode(token)}"
    }

    private fun getJson(url: String): JSONObject {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 5000
            readTimeout = 10000
            if (token.isNotEmpty()) setRequestProperty("X-Auth-Token", token)
        }
        try {
            val code = conn.responseCode
            val body = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) {
                val detail = runCatching { JSONObject(body).getString("error") }.getOrNull()
                throw ServerException("HTTP $code${detail?.let { ": $it" } ?: ""}")
            }
            return JSONObject(body)
        } finally {
            conn.disconnect()
        }
    }
}
