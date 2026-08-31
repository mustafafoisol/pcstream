package com.example.pcstream

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.pcstream.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var adapter: EntryAdapter

    private var client: ServerClient? = null
    private var currentPath: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        adapter = EntryAdapter(::onEntryClicked)
        binding.list.layoutManager = LinearLayoutManager(this)
        binding.list.adapter = adapter
        binding.list.addItemDecoration(DividerItemDecoration(this, DividerItemDecoration.VERTICAL))

        val prefs = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        binding.urlInput.setText(prefs.getString(KEY_URL, ""))
        binding.tokenInput.setText(prefs.getString(KEY_TOKEN, ""))

        binding.connectButton.setOnClickListener { connect() }
        binding.upButton.setOnClickListener { goUp() }
        binding.upButton.visibility = View.GONE

        if (!binding.urlInput.text.isNullOrBlank()) connect()
    }

    private fun connect() {
        val url = binding.urlInput.text.toString().trim()
        val token = binding.tokenInput.text.toString().trim()
        if (url.isEmpty()) {
            toast("Enter the server URL shown by serve.py")
            return
        }
        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_URL, url).putString(KEY_TOKEN, token).apply()

        client = ServerClient(url, token)
        currentPath = ""
        load("")
    }

    private fun load(path: String) {
        val c = client ?: return
        binding.statusText.text = "Loading…"
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    val host = c.ping()
                    host to c.list(path)
                }
            }
            result.onSuccess { (host, entries) ->
                currentPath = path
                adapter.submit(entries)
                binding.upButton.visibility = if (path.isEmpty()) View.GONE else View.VISIBLE
                binding.statusText.text =
                    "$host · /${path}".trimEnd('/') + "  (${entries.size} items)"
            }.onFailure { e ->
                adapter.submit(emptyList())
                binding.statusText.text = "Could not reach the server: ${e.message}"
            }
        }
    }

    private fun goUp() {
        if (currentPath.isEmpty()) return
        load(currentPath.substringBeforeLast('/', ""))
    }

    private fun onEntryClicked(entry: Entry) {
        val c = client ?: return
        if (entry.isDir) {
            load(entry.path)
            return
        }
        if (!entry.isMedia) {
            toast("${entry.name} is not a playable media file")
            return
        }
        startActivity(Intent(this, PlayerActivity::class.java).apply {
            putExtra(PlayerActivity.EXTRA_URL, c.mediaUrl(entry.path))
            putExtra(PlayerActivity.EXTRA_TITLE, entry.name)
        })
    }

    override fun onBackPressed() {
        if (currentPath.isNotEmpty()) goUp() else super.onBackPressed()
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    companion object {
        private const val PREFS = "pcstream"
        private const val KEY_URL = "url"
        private const val KEY_TOKEN = "token"
    }
}
