import { useEffect, useMemo, useState } from 'react'
import {
  FileUp, Upload, Trash2, Save, Loader2, X, GraduationCap, Pencil,
  RotateCcw, Plus, Factory,
} from 'lucide-react'
import {
  listAgentTraining, deleteAgentTraining, getTrainingSchemas,
  createTrainingEntry, updateTrainingEntry, restoreTrainingEntry, extractTraining,
} from '../../../services/api'
import { Loading, EmptyState, Badge } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Entrenamiento ESTRUCTURADO (Fase E1): el cliente llena CAMPOS por categoría (nunca texto
// libre al prompt). Las 6 plantillas de fábrica vienen sembradas: las "espejo" activas
// (tono, política, objeciones) y las adicionales desactivadas hasta que el cliente las
// revise. "Subir documento" → la IA propone los campos → el cliente revisa y guarda.
// NOTA: la INYECCIÓN al comportamiento llega en la fase siguiente (E2); hoy se gestiona.

export default function EmployeeTraining({ agent }) {
  const { runProtected, gateModal } = useAdminGate()
  const [docs, setDocs] = useState([])
  const [schemas, setSchemas] = useState(null)   // { order, schemas }
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)       // {mode:'edit'|'new'|'upload', doc?, category?, data?}

  const load = () => {
    setLoading(true)
    Promise.all([
      listAgentTraining(agent.id).catch(() => []),
      getTrainingSchemas().catch(() => null),
    ])
      .then(([d, s]) => { setDocs(d); setSchemas(s) })
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [agent.id])

  const byCategory = useMemo(() => {
    const map = {}
    for (const d of docs) {
      const key = d.category || '_legacy'
      ;(map[key] = map[key] || []).push(d)
    }
    return map
  }, [docs])

  const toggleActive = (doc) =>
    runProtected(async () => {
      await updateTrainingEntry(agent.id, doc.id, { active: !doc.active })
      toast.success(!doc.active ? 'Entrenamiento activado' : 'Entrenamiento desactivado')
      load()
    })

  const restore = (doc) =>
    runProtected(async () => {
      await restoreTrainingEntry(agent.id, doc.id)
      toast.success('Plantilla restaurada a fábrica')
      load()
    })

  const remove = (doc) =>
    runProtected(async () => {
      await deleteAgentTraining(agent.id, doc.id)
      toast.success('Entrenamiento eliminado')
      load()
    })

  if (loading) return <Loading label="Cargando entrenamiento…" />
  if (!schemas) return <EmptyState icon={GraduationCap} title="No se pudieron cargar los formularios" desc="Reintentá en un momento." />

  return (
    <div>
      {gateModal}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-lg font-600 text-ink">Entrenamiento de {agent.name}</h2>
          <p className="mt-0.5 text-sm text-slatey">
            Directivas que moldean cómo trabaja: se cargan por formulario (campos guiados), nunca texto suelto.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setModal({ mode: 'upload' })}
            className="inline-flex items-center gap-1.5 rounded-xl bg-white px-3.5 py-2 text-sm font-medium text-slatey ring-1 ring-mist hover:bg-mist"
          >
            <FileUp size={15} /> Subir documento
          </button>
          <button
            onClick={() => setModal({ mode: 'new' })}
            className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-hilton-700"
          >
            <Plus size={15} /> Nuevo entrenamiento
          </button>
        </div>
      </div>

      <div className="space-y-5">
        {schemas.order.map((cat) => {
          const spec = schemas.schemas[cat]
          const items = byCategory[cat] || []
          return (
            <section key={cat}>
              <div className="mb-2">
                <h3 className="font-serif text-base font-600 text-ink">{spec.label}</h3>
                <p className="text-xs text-slatey">{spec.hint}</p>
              </div>
              {items.length === 0 ? (
                <p className="rounded-xl border border-dashed border-stone-200 px-4 py-3 text-sm text-slatey">
                  Sin entrenamientos en esta categoría.
                </p>
              ) : (
                <div className="grid gap-2.5 lg:grid-cols-2">
                  {items.map((doc) => (
                    <div key={doc.id} className="rounded-2xl bg-white p-4 shadow-card">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <p className="font-600 text-ink">{doc.title}</p>
                            {doc.is_default && (
                              <Badge tone="blue"><span className="inline-flex items-center gap-1"><Factory size={11} /> Fábrica</span></Badge>
                            )}
                            <Badge tone={doc.active ? 'green' : 'gray'}>{doc.active ? 'Activo' : 'Inactivo'}</Badge>
                          </div>
                          <p className="mt-1 text-xs text-slatey">{summarize(doc, spec)}</p>
                        </div>
                        {/* Toggle activo */}
                        <button
                          onClick={() => toggleActive(doc)}
                          role="switch" aria-checked={doc.active}
                          className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
                            doc.active ? 'bg-hilton-600' : 'bg-stone-300'
                          }`}
                        >
                          <span className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                            doc.active ? 'translate-x-5' : 'translate-x-0.5'
                          }`} />
                        </button>
                      </div>
                      <div className="mt-3 flex items-center gap-1.5">
                        <button
                          onClick={() => setModal({ mode: 'edit', doc, category: doc.category, data: doc.data })}
                          className="inline-flex items-center gap-1 rounded-lg bg-mist px-2.5 py-1.5 text-xs font-medium text-slatey hover:bg-stone-100"
                        >
                          <Pencil size={12} /> Editar
                        </button>
                        {doc.is_default ? (
                          <button
                            onClick={() => restore(doc)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slatey hover:bg-mist"
                          >
                            <RotateCcw size={12} /> Restaurar fábrica
                          </button>
                        ) : (
                          <button
                            onClick={() => remove(doc)}
                            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slatey hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 size={12} /> Eliminar
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )
        })}

        {/* Documentos libres legado (sin formulario) */}
        {(byCategory._legacy || []).length > 0 && (
          <section>
            <h3 className="mb-2 font-serif text-base font-600 text-ink">Documentos libres (legado)</h3>
            <div className="grid gap-2.5 lg:grid-cols-2">
              {byCategory._legacy.map((doc) => (
                <div key={doc.id} className="flex items-start justify-between gap-3 rounded-2xl bg-white p-4 shadow-card">
                  <div className="min-w-0">
                    <p className="font-600 text-ink">{doc.title}</p>
                    {doc.excerpt && <p className="mt-0.5 line-clamp-2 text-sm text-slatey">{doc.excerpt}</p>}
                  </div>
                  <button onClick={() => remove(doc)} aria-label="Eliminar"
                          className="shrink-0 rounded-lg p-2 text-slatey hover:bg-red-50 hover:text-red-600">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {modal && (
        <TrainingModal
          agent={agent}
          schemas={schemas}
          modal={modal}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load() }}
          runProtected={runProtected}
        />
      )}
    </div>
  )
}

// Resumen corto del contenido para la card.
function summarize(doc, spec) {
  const d = doc.data || {}
  const listField = spec.fields.find((f) => f.type === 'list')
  if (listField) {
    const n = (d[listField.key] || []).length
    return `${n} ${n === 1 ? 'entrada' : 'entradas'}`
  }
  const parts = []
  if (d.trato) parts.push(`trato: ${d.trato}`)
  if (d.palabras_preferidas?.length) parts.push(`${d.palabras_preferidas.length} expresiones`)
  if (d.no_prometer?.length) parts.push(`${d.no_prometer.length} límites`)
  return parts.join(' · ') || 'Sin contenido'
}

// ───────────────────────────────────────────────────────────────────────────
// Modal: nuevo / editar / subir-documento→IA→formulario pre-llenado
// ───────────────────────────────────────────────────────────────────────────
function TrainingModal({ agent, schemas, modal, onClose, onSaved, runProtected }) {
  const isUpload = modal.mode === 'upload'
  const [category, setCategory] = useState(modal.category || schemas.order[0])
  const [data, setData] = useState(modal.data || {})
  const [file, setFile] = useState(null)
  const [text, setText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extracted, setExtracted] = useState(false)  // upload: ya propuso campos
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const spec = schemas.schemas[category]
  const showForm = modal.mode !== 'upload' || extracted

  const runExtract = () => {
    if (!file && !text.trim()) { setError('Elegí un archivo o pegá texto.'); return }
    setExtracting(true); setError('')
    runProtected(async () => {
      const res = await extractTraining(agent.id, { category, file, text: text.trim() || undefined })
      setData(res.data || {})
      setExtracted(true)
      toast.success('Campos propuestos por la IA — revisalos antes de guardar.')
    }).catch((e) => setError(e?.response?.data?.detail || 'No se pudo interpretar el documento.'))
      .finally(() => setExtracting(false))
  }

  const save = () => {
    setSaving(true); setError('')
    runProtected(async () => {
      let res
      if (modal.mode === 'edit') res = await updateTrainingEntry(agent.id, modal.doc.id, { data })
      else res = await createTrainingEntry(agent.id, { category, data })
      if (res.notes?.length) res.notes.forEach((n) => toast.info(n))
      else toast.success('Entrenamiento guardado')
      onSaved()
    }).catch((e) => setError(e?.response?.data?.detail || 'No se pudo guardar.'))
      .finally(() => setSaving(false))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <GraduationCap size={18} />
            </div>
            <h3 className="font-serif text-lg font-700 text-ink">
              {modal.mode === 'edit' ? `Editar · ${spec.label}` : isUpload ? 'Subir documento de entrenamiento' : 'Nuevo entrenamiento'}
            </h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        {/* Selector de categoría (solo al crear/subir) */}
        {modal.mode !== 'edit' && (
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-ink">Categoría</label>
            <select
              value={category}
              onChange={(e) => { setCategory(e.target.value); setData({}); setExtracted(false) }}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
            >
              {schemas.order.map((c) => (
                <option key={c} value={c}>{schemas.schemas[c].label}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slatey">{spec.hint}</p>
          </div>
        )}

        {/* Upload: archivo/texto → IA propone los campos */}
        {isUpload && !extracted && (
          <div className="space-y-3">
            <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-hilton-300 px-4 py-3 text-sm text-slatey hover:bg-hilton-50">
              <Upload size={16} />
              {file ? file.name : 'Elegí un archivo (PDF, .md o .txt)…'}
              <input type="file" accept=".pdf,.md,.markdown,.txt"
                     onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" />
            </label>
            <textarea
              value={text} onChange={(e) => setText(e.target.value)} rows={4}
              placeholder="…o pegá el texto acá"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
            <button
              onClick={runExtract} disabled={extracting}
              className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-hilton-700 disabled:opacity-60"
            >
              {extracting ? <Loader2 size={15} className="animate-spin" /> : <FileUp size={15} />}
              {extracting ? 'Interpretando…' : 'Interpretar con IA'}
            </button>
          </div>
        )}

        {/* Formulario genérico por schema */}
        {showForm && (
          <div className="space-y-4">
            {extracted && (
              <p className="rounded-xl bg-hilton-50 px-3.5 py-2.5 text-sm text-hilton-700">
                Campos propuestos por la IA a partir del documento. Revisá y corregí antes de guardar.
              </p>
            )}
            {spec.fields.map((f) => (
              <FieldRenderer key={f.key} field={f} value={data[f.key]} onChange={(v) => setData((prev) => ({ ...prev, [f.key]: v }))} />
            ))}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        {showForm && (
          <div className="mt-6 flex justify-end gap-2">
            <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">Cancelar</button>
            <button
              onClick={save} disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-hilton-700 disabled:opacity-60"
            >
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              Guardar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Renderizador genérico de campos (text / textarea / select / bool / tags / list)
// ───────────────────────────────────────────────────────────────────────────
const inputCls = 'w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100'

function FieldRenderer({ field, value, onChange }) {
  if (field.type === 'text') {
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-ink">{field.label}</label>
        <input value={value || ''} onChange={(e) => onChange(e.target.value)} className={inputCls} />
      </div>
    )
  }
  if (field.type === 'textarea') {
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-ink">{field.label}</label>
        <textarea value={value || ''} onChange={(e) => onChange(e.target.value)} rows={3} className={inputCls} />
      </div>
    )
  }
  if (field.type === 'select') {
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-ink">{field.label}</label>
        <select value={value ?? field.default ?? ''} onChange={(e) => onChange(e.target.value)} className={inputCls}>
          {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>
    )
  }
  if (field.type === 'bool') {
    return (
      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={value ?? field.default ?? false}
               onChange={(e) => onChange(e.target.checked)}
               className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-200" />
        {field.label}
      </label>
    )
  }
  if (field.type === 'tags') {
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-ink">{field.label}</label>
        <input
          value={(value || []).join(', ')}
          onChange={(e) => onChange(e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
          placeholder="separadas por coma"
          className={inputCls}
        />
      </div>
    )
  }
  if (field.type === 'list') {
    const rows = value || []
    const setRow = (i, k, v) => onChange(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
    return (
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink">{field.label}</label>
        <div className="space-y-2.5">
          {rows.map((row, i) => (
            <div key={i} className="rounded-xl border border-mist p-3">
              <div className="space-y-2">
                {field.item_fields.map((sub) => (
                  <FieldRenderer key={sub.key} field={sub} value={row[sub.key]} onChange={(v) => setRow(i, sub.key, v)} />
                ))}
              </div>
              <button
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slatey hover:text-red-600"
              >
                <Trash2 size={12} /> Quitar
              </button>
            </div>
          ))}
          <button
            onClick={() => onChange([...rows, {}])}
            className="inline-flex items-center gap-1.5 rounded-xl bg-mist px-3 py-2 text-sm font-medium text-slatey hover:bg-stone-100"
          >
            <Plus size={14} /> Agregar
          </button>
        </div>
      </div>
    )
  }
  return null
}
