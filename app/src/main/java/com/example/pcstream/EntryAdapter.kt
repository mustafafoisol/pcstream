package com.example.pcstream

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.example.pcstream.databinding.ItemEntryBinding
import java.util.Locale

class EntryAdapter(private val onClick: (Entry) -> Unit) :
    RecyclerView.Adapter<EntryAdapter.VH>() {

    private var items: List<Entry> = emptyList()

    fun submit(list: List<Entry>) {
        items = list
        notifyDataSetChanged()
    }

    class VH(val binding: ItemEntryBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(ItemEntryBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun getItemCount() = items.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        val e = items[position]
        holder.binding.name.text = if (e.isDir) "📁 ${e.name}" else e.name
        holder.binding.meta.text = when {
            e.isDir -> "folder"
            e.isMedia -> "${humanSize(e.size)} · tap to stream"
            else -> "${humanSize(e.size)} · ${e.mime}"
        }
        holder.itemView.setOnClickListener { onClick(e) }
    }

    private fun humanSize(bytes: Long): String {
        if (bytes < 1024) return "$bytes B"
        val units = arrayOf("KB", "MB", "GB", "TB")
        var value = bytes.toDouble() / 1024
        var i = 0
        while (value >= 1024 && i < units.lastIndex) {
            value /= 1024
            i++
        }
        return String.format(Locale.US, "%.1f %s", value, units[i])
    }
}
