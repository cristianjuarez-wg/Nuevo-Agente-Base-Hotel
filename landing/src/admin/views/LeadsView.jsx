import { useEffect, useState } from 'react'
import { UserPlus, RefreshCw, Mail, Phone, Flame, Trash2, Pencil, X, Save, Loader2, MessageCircle, MessageSquare, List, LayoutGrid } from 'lucide-react'
import { listLeads, deleteLead, updateLead } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, OriginBadge, Loading, EmptyState, formatDate, WhatsAppDot,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import ChatTranscript from '../components/ChatTranscript'
import { FilterChip, FilterGroupLabel, FilterDivider } from '../components/FilterChip'
import { useTableControls } from '../hooks/useTableControls'
import KanbanBoard from './KanbanBoard'

const TYPE_FILTERS = [
  { id: 'all', label: 'Todos' },
  { id: 'CALIENTE', label: 'Calientes' },
  { id: 'TIBIO', label: 'Tibios' },
  { id: 'FRIO', label: 'Fríos' },
]

export function TypeBadge({ type }) {
  const t = (type || '').toUpperCase()
  const map = { CALIENTE: 'red', TIBIO: 'amber', FRIO: 'blue' }
  return <Badge tone={map[t] || 'gray'}>{t || '—'}</Badge>
}

// Distintivo para leads que YA reservaron (convertidos). Se muestra junto al TypeBadge
// para que el equipo comercial los identifique de un vistazo.
export function WonBadge({ status, stage }) {
  const won = status === 'converted' || stage === 'won'
  if (!won) return null
  return <Badge tone="green">Reservó</Badge>
}

export function ScoreBar({ score }) {
  const s = Number(score) || 0
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-mist">
        <div className="h-full rounded-full bg-hilton-500" style={{ width: `${s * 10}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slatey">{s}/10</span>
    </div>
  )
}

// Aplana el lead anidado del backend a una fila plana.
function flatten(lead) {
  const c = lead.contact_info || {}
  const cl = lead.classification || {}
  const ti = lead.travel_interest || {}
  const md = lead.metadata || {}
  const name = [c.name, c.last_name].filter(Boolean).join(' ') || 'Sin nombre'
  return {
    _key: lead.id,
    id: lead.id,
    name,
    firstName: c.name || '',
    lastName: c.last_name || '',
    email: c.email,
    phone: c.phone,
    type: cl.lead_type,
    score: cl.interest_score,
    interest: ti.main_interest,
    status: md.status,
    kanbanStage: lead.kanban?.stage,
    origin: md.origin,
    created_at: md.created_at,
    whatsappLinked: lead.whatsapp_linked,
    sessionId: lead.session_id,
  }
}

export default function LeadsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)
  const [filter, setFilter] = useState('all')
  const [showAll, setShowAll] = useState(false)  // false = solo calificados (con nombre)
  const [viewMode, setViewMode] = useState('list')  // 'list' | 'board'
  const [editLead, setEditLead] = useState(null)
  const [chatLead, setChatLead] = useState(null)  // lead cuyo historial de chat se está viendo

  const load = (includeUnnamed = showAll) => {
    setLoading(true)
    listLeads(includeUnnamed)
      .then((d) => {
        const arr = Array.isArray(d) ? d : d?.leads || []
        setRows(arr.map(flatten))
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load(showAll) }, [showAll])

  const handleDelete = async (r) => {
    if (!window.confirm(`¿Eliminar el lead de ${r.name}? Esta acción no se puede deshacer.`)) return
    setDeletingId(r.id)
    try {
      await deleteLead(r.id)
      setRows((prev) => prev.filter((x) => x.id !== r.id))
      toast.success(`Lead de ${r.name} eliminado`)
    } catch {
      toast.error('No se pudo eliminar el lead. Intentá de nuevo.')
    } finally {
      setDeletingId(null)
    }
  }

  const DeleteButton = ({ r }) => (
    <button
      onClick={() => handleDelete(r)}
      disabled={deletingId === r.id}
      title="Eliminar lead"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
    >
      <Trash2 size={15} />
    </button>
  )

  const ChatButton = ({ r }) => (
    <button
      onClick={() => setChatLead(r)}
      title="Ver conversación"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-hilton-50 hover:text-hilton-700"
    >
      <MessageSquare size={15} />
    </button>
  )

  const EditButton = ({ r }) => (
    <button
      onClick={() => setEditLead(r)}
      title="Editar datos"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-mist hover:text-ink"
    >
      <Pencil size={15} />
    </button>
  )

  const columns = [
    { key: 'name', label: 'Nombre', sortable: true, render: (r) => <span className="font-medium text-ink">{r.name}</span> },
    { key: 'contact', label: 'Contacto', render: (r) => (
      <div className="space-y-0.5 text-xs text-slatey">
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} title="Se comunicó por WhatsApp" /></p>}
        {!r.email && !r.phone && '—'}
      </div>
    ) },
    { key: 'interest', label: 'Interés', render: (r) => r.interest || '—' },
    { key: 'origin', label: 'Origen', render: (r) => <OriginBadge origin={r.origin} /> },
    { key: 'type', label: 'Tipo', render: (r) => (
      <div className="flex items-center gap-1.5"><TypeBadge type={r.type} /><WonBadge status={r.status} stage={r.kanbanStage} /></div>
    ) },
    { key: 'score', label: 'Score', sortable: true, render: (r) => <ScoreBar score={r.score} /> },
    { key: 'created_at', label: 'Fecha', sortable: true, render: (r) => formatDate(r.created_at) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1"><ChatButton r={r} /><EditButton r={r} /><DeleteButton r={r} /></div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-ink">{r.name}</span>
        <div className="flex items-center gap-1.5">
          <OriginBadge origin={r.origin} />
          <WonBadge status={r.status} stage={r.kanbanStage} />
          <TypeBadge type={r.type} />
        </div>
      </div>
      {r.interest && <p className="text-sm text-slatey">{r.interest}</p>}
      <div className="mt-2 space-y-0.5 text-xs text-slatey">
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} title="Se comunicó por WhatsApp" /></p>}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <ScoreBar score={r.score} />
        <div className="flex items-center gap-1"><ChatButton r={r} /><EditButton r={r} /><DeleteButton r={r} /></div>
      </div>
    </div>
  )

  // Chips por temperatura → búsqueda + orden + paginación.
  const byType = filter === 'all' ? rows : rows.filter((r) => (r.type || '').toUpperCase() === filter)
  const counts = rows.reduce((acc, r) => {
    acc.all += 1
    const t = (r.type || '').toUpperCase()
    if (t) acc[t] = (acc[t] || 0) + 1
    return acc
  }, { all: 0 })
  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } =
    useTableControls(byType, {
      searchKeys: ['name', 'email', 'phone', 'interest'],
      pageSize: 50,
      sortAccessors: {
        name: (r) => r.name || '',
        score: (r) => Number(r.score) || 0,
        created_at: (r) => r.created_at || '',
      },
    })

  return (
    <div>
      <PageHeader
        title="Leads"
        subtitle="Interesados captados por el agente durante las conversaciones."
        right={
          <button onClick={load} className="btn-secondary px-4 py-2 text-xs">
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />

      {/* Vista: Lista / Tablero (kanban). Es una decisión de presentación, separada de los
          filtros — por eso va en su propia fila con un segmented control. */}
      <div className="mb-4 inline-flex rounded-xl bg-mist p-1">
        <button
          onClick={() => setViewMode('list')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
            viewMode === 'list' ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey hover:text-ink'
          }`}
        >
          <List size={14} /> Lista
        </button>
        <button
          onClick={() => setViewMode('board')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
            viewMode === 'board' ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey hover:text-ink'
          }`}
        >
          <LayoutGrid size={14} /> Tablero
        </button>
      </div>

      {viewMode === 'board' ? (
        <KanbanBoard />
      ) : loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={UserPlus} title="Aún no hay leads" desc="Cuando el agente capte interesados, aparecerán acá." />
      ) : (
        <>
          {/* Banda de filtros unificada: Alcance · Temperatura · buscador. Chips homogéneos
              (mismo lenguaje visual que Operaciones), con etiquetas de grupo y divisor sutil. */}
          <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
            {/* Alcance: calificados (con nombre) vs todos los contactos captados. */}
            <FilterGroupLabel>Alcance</FilterGroupLabel>
            <FilterChip active={!showAll} onClick={() => setShowAll(false)} label="Calificados" />
            <FilterChip active={showAll} onClick={() => setShowAll(true)} label="Todos los contactos" icon={MessageCircle} />

            <FilterDivider />

            {/* Temperatura del lead. */}
            <FilterGroupLabel>Temperatura</FilterGroupLabel>
            {TYPE_FILTERS.map((f) => (
              <FilterChip
                key={f.id}
                active={filter === f.id}
                onClick={() => setFilter(f.id)}
                label={f.label}
                count={counts[f.id] ?? 0}
              />
            ))}

            {/* Buscador: a la derecha en desktop, ancho completo en mobile. */}
            <div className="w-full sm:ml-auto sm:w-72">
              <SearchInput value={query} onChange={setQuery} placeholder="Buscar por nombre, email o interés…" />
            </div>
          </div>
          {total === 0 ? (
            <EmptyState icon={UserPlus} title="Sin leads en esta vista" desc="Probá con otro filtro o búsqueda." />
          ) : (
            <>
              <ResponsiveTable columns={columns} rows={pageRows} renderCard={renderCard} sort={sort} onSort={toggleSort} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {editLead && (
        <EditLeadModal
          lead={editLead}
          onClose={() => setEditLead(null)}
          onSaved={() => { setEditLead(null); load() }}
        />
      )}

      {chatLead && (
        <LeadChatDrawer lead={chatLead} onClose={() => setChatLead(null)} />
      )}
    </div>
  )
}

// ── Panel lateral con la charla con Aura que generó el lead ──────────────────
function LeadChatDrawer({ lead, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-card-lg animate-slide-up">
        <div className="flex items-start justify-between border-b border-mist px-5 py-4">
          <div>
            <p className="font-serif text-lg font-700 text-hilton-700">{lead.name}</p>
            <p className="mt-0.5 text-sm text-slatey">Conversación con Aura</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <TypeBadge type={lead.type} />
              <WonBadge status={lead.status} stage={lead.kanbanStage} />
              {lead.interest && <span className="text-xs text-slatey">{lead.interest}</span>}
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ChatTranscript sessionId={lead.sessionId} />
        </div>
      </aside>
    </div>
  )
}

// ── Modal de edición de datos del lead ──────────────────────────────────────
function EditLeadModal({ lead, onClose, onSaved }) {
  const [firstName, setFirstName] = useState(lead.firstName || '')
  const [lastName, setLastName] = useState(lead.lastName || '')
  const [email, setEmail] = useState(lead.email || '')
  const [phone, setPhone] = useState(lead.phone || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      await updateLead(lead.id, {
        name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim(),
      })
      toast.success('Datos del lead actualizados')
      onSaved()
    } catch (e) {
      const msg = e?.response?.data?.detail || 'No se pudo guardar. Intentá de nuevo.'
      setError(msg)
      setSaving(false)
    }
  }

  return (
    <Modal title="Editar lead" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nombre" value={firstName} onChange={setFirstName} placeholder="Nombre" />
          <Field label="Apellido" value={lastName} onChange={setLastName} placeholder="Apellido" />
        </div>
        <Field label="Email" value={email} onChange={setEmail} placeholder="email@ejemplo.com" type="email" />
        <Field label="Teléfono" value={phone} onChange={setPhone} placeholder="+54 9 11 …" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">Cancelar</button>
          <button onClick={save} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
          </button>
        </div>
      </div>
    </Modal>
  )
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">{title}</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        type={type} value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
    </label>
  )
}
