import { useEffect, useState } from 'react'
import { FileUp, Upload, Trash2, FileText, Save, Loader2, X, GraduationCap } from 'lucide-react'
import {
  listAgentTraining, uploadAgentTraining, addAgentTrainingText, deleteAgentTraining,
} from '../../../services/api'
import { Loading, EmptyState, formatDate } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Entrenamiento por agente: documentos que moldean CÓMO se comporta (tono, protocolos,
// políticas de marca). Distinto del Conocimiento del negocio. Reusa el patrón de subida
// PDF/MD/TXT del repositorio de conocimiento, pero acotado a ESTE agente.
const SOURCE_LABEL = { pdf: 'PDF', markdown: 'Markdown', text: 'Texto' }

export default function EmployeeTraining({ agent }) {
  const { runProtected, gateModal } = useAdminGate()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)

  const load = () => {
    setLoading(true)
    listAgentTraining(agent.id)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [agent.id])

  const remove = (doc) =>
    runProtected(async () => {
      await deleteAgentTraining(agent.id, doc.id)
      toast.success('Documento eliminado')
      load()
    })

  return (
    <div>
      {gateModal}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-lg font-600 text-ink">Entrenamiento de {agent.name}</h2>
          <p className="mt-0.5 text-sm text-slatey">
            Documentos que moldean cómo se comporta (tono, protocolos, políticas de marca).
          </p>
        </div>
        <button
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-hilton-700"
        >
          <FileUp size={15} /> Nuevo documento
        </button>
      </div>

      {loading ? (
        <Loading label="Cargando entrenamiento…" />
      ) : docs.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title="Sin documentos de entrenamiento"
          desc="Subí manuales de atención, protocolos o guías de tono para capacitar a este agente."
        />
      ) : (
        <ul className="space-y-2.5">
          {docs.map((d) => (
            <li key={d.id} className="flex items-start justify-between gap-3 rounded-2xl bg-white p-4 shadow-card">
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
                  <FileText size={18} />
                </div>
                <div className="min-w-0">
                  <p className="font-600 text-ink">{d.title}</p>
                  {d.excerpt && <p className="mt-0.5 line-clamp-2 text-sm text-slatey">{d.excerpt}</p>}
                  <p className="mt-1 text-xs text-slatey">
                    {SOURCE_LABEL[d.source] || d.source}
                    {d.created_at ? ` · ${formatDate(d.created_at)}` : ''}
                  </p>
                </div>
              </div>
              <button
                onClick={() => remove(d)}
                aria-label="Eliminar"
                className="shrink-0 rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600"
              >
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <TrainingModal
          agent={agent}
          onClose={() => setAdding(false)}
          onSaved={() => { setAdding(false); load() }}
          runProtected={runProtected}
        />
      )}
    </div>
  )
}

function TrainingModal({ agent, onClose, onSaved, runProtected }) {
  const [mode, setMode] = useState('pdf')   // 'pdf' | 'text'
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = () => {
    if (!title.trim()) { setError('Poné un título.'); return }
    if (mode === 'pdf' && !file) { setError('Elegí un archivo.'); return }
    if (mode === 'text' && !text.trim()) { setError('Pegá el texto.'); return }
    setSaving(true); setError('')
    runProtected(async () => {
      if (mode === 'pdf') await uploadAgentTraining(agent.id, { title, file })
      else await addAgentTrainingText(agent.id, { title, text })
      toast.success('Documento agregado')
      onSaved()
    }).catch((e) => {
      setError(e?.response?.data?.detail || 'No se pudo guardar.')
    }).finally(() => setSaving(false))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <FileUp size={18} />
            </div>
            <h3 className="font-serif text-lg font-700 text-ink">Nuevo documento de entrenamiento</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        <div className="space-y-4">
          <div className="flex gap-1 rounded-xl bg-mist p-1">
            {[['pdf', 'Subir archivo'], ['text', 'Pegar texto']].map(([id, label]) => (
              <button
                key={id} onClick={() => setMode(id)}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  mode === id ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Título</label>
            <input
              value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej: Protocolo de quejas, Tono de marca…"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </div>

          {mode === 'pdf' ? (
            <div>
              <label className="mb-1 block text-sm font-medium text-ink">Archivo (PDF o Markdown)</label>
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-hilton-300 px-4 py-3 text-sm text-slatey hover:bg-hilton-50">
                <Upload size={16} />
                {file ? file.name : 'Elegí un archivo (PDF o .md)…'}
                <input
                  type="file" accept=".pdf,.md,.markdown,.txt"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="hidden"
                />
              </label>
            </div>
          ) : (
            <div>
              <label className="mb-1 block text-sm font-medium text-ink">Texto</label>
              <textarea
                value={text} onChange={(e) => setText(e.target.value)} rows={6}
                placeholder="Pegá acá el contenido…"
                className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
              />
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button onClick={onClose} className="text-sm font-medium text-slatey hover:text-ink">Cancelar</button>
          <button
            onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}
