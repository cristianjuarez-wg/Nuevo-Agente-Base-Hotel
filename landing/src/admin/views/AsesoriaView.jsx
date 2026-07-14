import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { GraduationCap, RefreshCw, Upload, Trash2, FileText, Loader2, BrainCircuit, Eye, X } from 'lucide-react'
import {
  listManagementDocs, uploadManagementDoc, setManagementDocStatus, deleteManagementDoc,
  resetAdvisorMemory, getManagementDocContent,
} from '../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDate } from '../ui'
import { toast } from '../toast'

// Repositorio de conocimiento del CONSULTOR de gerencia: libros/documentos de gestión
// hotelera que entrenan al agente del dueño. Separado del conocimiento de Aura (huéspedes).
export default function AsesoriaView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [viewDoc, setViewDoc] = useState(null)  // documento cuyo contenido se está viendo
  const fileInput = useRef(null)

  const load = () => {
    setLoading(true)
    listManagementDocs()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const onPick = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!/\.(pdf|md|markdown|txt)$/i.test(file.name)) {
      toast.error('Formatos aceptados: PDF, Markdown (.md) o texto (.txt).')
      return
    }
    setUploading(true)
    try {
      const r = await uploadManagementDoc(file)
      toast.success(`"${file.name}" procesado (${r.chunks_created} fragmentos)`)
      load()
    } catch {
      toast.error('No se pudo procesar el documento. Probá de nuevo.')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const toggle = async (d) => {
    const next = d.status === 'active' ? 'inactive' : 'active'
    setBusy(d.filename)
    try {
      await setManagementDocStatus(d.filename, next)
      load()
      toast.success(next === 'active' ? 'Documento activado' : 'Documento desactivado')
    } catch {
      toast.error('No se pudo cambiar el estado')
    } finally {
      setBusy(null)
    }
  }

  const remove = async (d) => {
    if (!window.confirm(`¿Eliminar "${d.filename}" del entrenamiento del consultor?`)) return
    setBusy(d.filename)
    try {
      await deleteManagementDoc(d.filename)
      setRows((prev) => prev.filter((x) => x.filename !== d.filename))
      toast.success('Documento eliminado')
    } catch {
      toast.error('No se pudo eliminar')
    } finally {
      setBusy(null)
    }
  }

  const doReset = async () => {
    setResetting(true)
    try {
      const r = await resetAdvisorMemory()
      toast.success(`Memoria reiniciada (${r.messages_cleared || 0} mensajes, ${r.plans_cleared || 0} planes)`)
      setConfirmReset(false)
    } catch {
      toast.error('No se pudo reiniciar la memoria del asesor')
    } finally {
      setResetting(false)
    }
  }

  const columns = [
    { key: 'filename', label: 'Documento', render: (r) => (
      <button onClick={() => setViewDoc(r)} title="Ver contenido"
              className="flex items-center gap-2 text-left font-medium text-ink transition hover:text-hilton-700">
        <FileText size={15} className="text-hilton-500" />
        <span className="underline-offset-2 hover:underline">{r.filename}</span>
      </button>
    ) },
    { key: 'uploaded_at', label: 'Subido', render: (r) => (
      <span className="text-xs text-slatey tabular-nums">
        {r.uploaded_at && r.uploaded_at !== 'unknown' ? formatDate(r.uploaded_at) : '—'}
      </span>
    ) },
    { key: 'status', label: 'Estado', render: (r) => (
      <button onClick={() => toggle(r)} disabled={busy === r.filename} className="disabled:opacity-50">
        {r.status === 'active'
          ? <Badge tone="green">Activo</Badge>
          : <Badge tone="gray">Inactivo</Badge>}
      </button>
    ) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1">
        <button onClick={() => setViewDoc(r)} title="Ver contenido"
                className="rounded-lg p-2 text-slatey transition hover:bg-hilton-50 hover:text-hilton-700">
          <Eye size={15} />
        </button>
        <button onClick={() => remove(r)} disabled={busy === r.filename} title="Eliminar"
                className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
          <Trash2 size={15} />
        </button>
      </div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <button onClick={() => setViewDoc(r)} className="flex items-center gap-2 text-left font-medium text-ink hover:text-hilton-700">
          <FileText size={15} className="text-hilton-500" /><span className="hover:underline">{r.filename}</span>
        </button>
        {r.uploaded_at && r.uploaded_at !== 'unknown' && (
          <span className="text-xs text-slatey tabular-nums">{formatDate(r.uploaded_at)}</span>
        )}
      </div>
      <div className="flex items-center justify-between">
        <button onClick={() => toggle(r)} disabled={busy === r.filename}>
          {r.status === 'active' ? <Badge tone="green">Activo</Badge> : <Badge tone="gray">Inactivo</Badge>}
        </button>
        <div className="flex items-center gap-1">
          <button onClick={() => setViewDoc(r)} className="rounded-lg p-2 text-slatey hover:bg-hilton-50 hover:text-hilton-700">
            <Eye size={15} />
          </button>
          <button onClick={() => remove(r)} disabled={busy === r.filename}
                  className="rounded-lg p-2 text-slatey hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
            <Trash2 size={15} />
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Asesor de gerencia"
        subtitle="Subí libros y documentos de gestión hotelera, revenue management o finanzas (PDF o Markdown). El asesor de gerencia (por WhatsApp) los usa para fundamentar sus recomendaciones, cruzándolos con los datos reales del hotel. Es independiente del conocimiento del agente de huéspedes."
        right={
          <div className="flex items-center gap-2">
            <button onClick={load} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>
            <button onClick={() => fileInput.current?.click()} disabled={uploading}
                    className="btn-primary px-4 py-2 text-xs disabled:opacity-60">
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {uploading ? 'Procesando…' : 'Subir documento'}
            </button>
            <input ref={fileInput} type="file" accept=".pdf,.md,.markdown,.txt" className="hidden" onChange={onPick} />
          </div>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Sin material de entrenamiento todavía"
                    desc="Subí un PDF o un Markdown (.md) — ej. un libro de gestión hotelera — para que el consultor pueda apoyarse en él." />
      ) : (
        <ResponsiveTable columns={columns} rows={rows.map((r) => ({ ...r, _key: r.filename }))} renderCard={renderCard} />
      )}

      {/* Memoria del asesor: el vínculo de largo plazo con el CEO (historial + planes). */}
      <div className="mt-8 rounded-2xl border border-hilton-100 bg-white p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <BrainCircuit size={18} />
            </div>
            <div>
              <p className="font-serif text-base font-700 text-ink">Memoria del asesor</p>
              <p className="mt-0.5 max-w-xl text-sm text-slatey">
                El asesor recuerda toda la relación con el dueño/CEO (conversaciones y planes de
                acción acordados) para darle continuidad. Reiniciar la memoria arranca el vínculo
                de cero — no borra los documentos de entrenamiento de arriba.
              </p>
            </div>
          </div>
          <button onClick={() => setConfirmReset(true)}
                  className="rounded-xl border border-red-200 px-4 py-2 text-xs font-medium text-red-600 transition hover:bg-red-50">
            Reiniciar memoria
          </button>
        </div>
      </div>

      {confirmReset && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <div className="absolute inset-0 bg-ink/40" onClick={() => !resetting && setConfirmReset(false)} />
          <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
            <h3 className="font-serif text-lg font-700 text-ink">Reiniciar la memoria del asesor</h3>
            <p className="mt-2 text-sm text-slatey">
              Esto borra <strong>toda la conversación y los planes</strong> que el asesor recuerda
              del dueño/CEO. No afecta los documentos de entrenamiento. <strong>No se puede deshacer.</strong>
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirmReset(false)} disabled={resetting}
                      className="btn-secondary px-4 py-2 text-sm disabled:opacity-60">Cancelar</button>
              <button onClick={doReset} disabled={resetting}
                      className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60">
                {resetting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                Reiniciar memoria
              </button>
            </div>
          </div>
        </div>
      )}

      {viewDoc && <DocViewerDrawer doc={viewDoc} onClose={() => setViewDoc(null)} />}
    </div>
  )
}

// Panel lateral que muestra el contenido del documento (reconstruido desde el RAG).
// Renderiza Markdown con react-markdown; los .md se ven con su formato.
function DocViewerDrawer({ doc, onClose }) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true); setError(false)
    getManagementDocContent(doc.filename)
      .then((d) => { if (alive) setContent(d.content || '') })
      .catch(() => { if (alive) setError(true) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [doc.filename])

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-card-lg animate-slide-up">
        <div className="flex items-start justify-between border-b border-mist px-5 py-4">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-hilton-500" />
            <div>
              <p className="font-serif text-base font-700 text-ink">{doc.filename}</p>
              <p className="text-xs text-slatey">Material de entrenamiento del asesor</p>
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <Loading label="Cargando documento…" />
          ) : error ? (
            <EmptyState icon={FileText} title="No se pudo cargar el contenido"
                        desc="Probá de nuevo. Si el documento se subió como PDF escaneado (sin texto), puede no tener contenido legible." />
          ) : (
            <div className="prose-doc">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}
