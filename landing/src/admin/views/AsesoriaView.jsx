import { useEffect, useRef, useState } from 'react'
import { GraduationCap, RefreshCw, Upload, Trash2, FileText, Loader2 } from 'lucide-react'
import {
  listManagementDocs, uploadManagementDoc, setManagementDocStatus, deleteManagementDoc,
} from '../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState } from '../ui'
import { toast } from '../toast'

// Repositorio de conocimiento del CONSULTOR de gerencia: libros/documentos de gestión
// hotelera que entrenan al agente del dueño. Separado del conocimiento de Aura (huéspedes).
export default function AsesoriaView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(null)
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
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('Solo se aceptan archivos PDF.')
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

  const columns = [
    { key: 'filename', label: 'Documento', render: (r) => (
      <span className="flex items-center gap-2 font-medium text-ink">
        <FileText size={15} className="text-hilton-500" />{r.filename}
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
      <button onClick={() => remove(r)} disabled={busy === r.filename} title="Eliminar"
              className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
        <Trash2 size={15} />
      </button>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-2 font-medium text-ink">
          <FileText size={15} className="text-hilton-500" />{r.filename}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <button onClick={() => toggle(r)} disabled={busy === r.filename}>
          {r.status === 'active' ? <Badge tone="green">Activo</Badge> : <Badge tone="gray">Inactivo</Badge>}
        </button>
        <button onClick={() => remove(r)} disabled={busy === r.filename}
                className="rounded-lg p-2 text-slatey hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Asesoría — Entrenamiento del consultor"
        subtitle="Subí libros y documentos de gestión hotelera, revenue management o finanzas. El asesor de gerencia (por WhatsApp) los usa para fundamentar sus recomendaciones, cruzándolos con los datos reales del hotel. Es independiente del conocimiento del agente de huéspedes."
        right={
          <div className="flex items-center gap-2">
            <button onClick={load} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>
            <button onClick={() => fileInput.current?.click()} disabled={uploading}
                    className="btn-primary px-4 py-2 text-xs disabled:opacity-60">
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {uploading ? 'Procesando…' : 'Subir PDF'}
            </button>
            <input ref={fileInput} type="file" accept="application/pdf" className="hidden" onChange={onPick} />
          </div>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={GraduationCap} title="Sin material de entrenamiento todavía"
                    desc="Subí un PDF (ej. un libro de gestión hotelera) para que el consultor pueda apoyarse en él." />
      ) : (
        <ResponsiveTable columns={columns} rows={rows.map((r) => ({ ...r, _key: r.filename }))} renderCard={renderCard} />
      )}
    </div>
  )
}
