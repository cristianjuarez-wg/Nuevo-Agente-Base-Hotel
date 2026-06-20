import { useRef, useState } from 'react'
import { Upload, Link2, X, Loader2 } from 'lucide-react'
import { uploadKnowledgeImage, MEDIA_BASE } from '../../services/api'

// Resuelve una ruta /media/... a URL absoluta para el preview.
function resolveUrl(url) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  return `${MEDIA_BASE}${url}`
}

/**
 * Input de imagen: acepta URL pegada O subida de archivo (que devuelve una URL /media/...).
 * Props: value (url string), onChange(url)
 */
export default function ImageInput({ value, onChange }) {
  const fileRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const { url } = await uploadKnowledgeImage(file)
      onChange(url)
    } catch (err) {
      setError('No se pudo subir la imagen.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Link2 size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slatey" />
          <input
            type="url"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Pegá una URL de imagen…"
            className="w-full rounded-xl border border-hilton-200 py-2.5 pl-9 pr-3 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
          />
        </div>
        <span className="text-center text-xs text-slatey">o</span>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm font-medium text-hilton-700 transition hover:bg-hilton-50 disabled:opacity-60"
        >
          {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          {uploading ? 'Subiendo…' : 'Subir archivo'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={handleFile}
          className="hidden"
        />
      </div>

      {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}

      {value && (
        <div className="relative mt-3 inline-block">
          <img
            src={resolveUrl(value)}
            alt="Vista previa"
            className="h-28 w-auto rounded-xl border border-hilton-100 object-cover"
          />
          <button
            type="button"
            onClick={() => onChange('')}
            aria-label="Quitar imagen"
            className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-ink text-white shadow-card"
          >
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  )
}
