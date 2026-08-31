package com.example.pcstream

import android.os.Bundle
import android.view.WindowManager
import android.widget.Toast
import androidx.annotation.OptIn
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import com.example.pcstream.databinding.ActivityPlayerBinding

@OptIn(UnstableApi::class)
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private var player: ExoPlayer? = null
    private var startPositionMs: Long = 0L
    private var playWhenReady: Boolean = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        savedInstanceState?.let {
            startPositionMs = it.getLong(STATE_POSITION)
            playWhenReady = it.getBoolean(STATE_PLAY_WHEN_READY, true)
        }
        title = intent.getStringExtra(EXTRA_TITLE) ?: getString(R.string.app_name)
    }

    private fun initPlayer() {
        val url = intent.getStringExtra(EXTRA_URL)
        if (url.isNullOrEmpty()) {
            Toast.makeText(this, "No stream URL", Toast.LENGTH_LONG).show()
            finish()
            return
        }
        val exo = ExoPlayer.Builder(this).build()
        binding.playerView.player = exo
        exo.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                Toast.makeText(
                    this@PlayerActivity,
                    "Playback failed: ${error.errorCodeName}",
                    Toast.LENGTH_LONG
                ).show()
            }
        })
        exo.setMediaItem(MediaItem.fromUri(url))
        exo.seekTo(startPositionMs)
        exo.playWhenReady = playWhenReady
        exo.prepare()
        player = exo
    }

    private fun releasePlayer() {
        player?.let {
            startPositionMs = it.currentPosition
            playWhenReady = it.playWhenReady
            it.release()
        }
        player = null
        binding.playerView.player = null
    }

    // Android 10 can hand the foreground to another app at any time, so the
    // player is created in onStart and released in onStop.
    override fun onStart() {
        super.onStart()
        initPlayer()
    }

    override fun onStop() {
        super.onStop()
        releasePlayer()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        player?.let {
            outState.putLong(STATE_POSITION, it.currentPosition)
            outState.putBoolean(STATE_PLAY_WHEN_READY, it.playWhenReady)
        }
    }

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_TITLE = "title"
        private const val STATE_POSITION = "position"
        private const val STATE_PLAY_WHEN_READY = "playWhenReady"
    }
}
