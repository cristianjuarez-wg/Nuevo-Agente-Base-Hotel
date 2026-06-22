import { useEffect, useState } from 'react'
import { UserPlus, RefreshCw, Mail, Phone, Flame, Trash2, Pencil, X, Save, Loader2 } from 'lucide-react'
import { listLeads, deleteLead, updateLead } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, OriginBadge, Loading, EmptyState, formatDate, WhatsAppDot,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import { useTableControls } from '../hooks/useTableControls'

const TYPE_FILTERS = [
  { id: 'all', label: 'Todos' },
  { id: 'CALIENTE', label: 'Calientes' },
  { id: 'TIBIO', label: 'Tibios' },
  { id: 'FRIO', label: 'Fríos' },
]

function TypeBadge({ type }) {
  const t = (type || '').toUpperCase()
  const map = { CALIENTE: 'red', TIBIO: 'amber', FRIO: 'blue' }
  return <Badge tone={map[t] || 'gray'}>{t || '—'}</Badge>
}

function ScoreBar({ score }) {
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
    origin: md.origin,
    created_at: md.created_at,
    whatsappLinked: lead.whatsapp_linked,
  }
}

export default function LeadsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)
  const [filter, setFilter] = useState('all')
  const [editLead, setEditLead] = useState(null)

  const load = () => {
    setLoading(true)
    listLeads()
      .then((d) => {
        const arr = Array.isArray(d) ? d : d?.leads || []
        setRows(arr.map(flatten))
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

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
    { key: 'type', label: 'Tipo', render: (r) => <TypeBadge type={r.type} /> },
    { key: 'score', label: 'Score', sortable: true, render: (r) => <ScoreBar score={r.score} /> },
    { key: 'created_at', label: 'Fecha', sortable: true, render: (r) => formatDate(r.created_at) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1"><EditButton r={r} /><DeleteButton r={r} /></div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-ink">{r.name}</span>
        <div className="flex items-center gap-1.5">
          <OriginBadge origin={r.origin} />
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
        <div className="flex items-center gap-1"><EditButton r={r} /><DeleteButton r={r} /></div>
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
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={UserPlus} title="Aún no hay leads" desc="Cuando el agente capte interesados, aparecerán acá." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${
                  filter === f.id ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
                }`}
              >
                {f.label} <span className="tabular-nums opacity-70">({counts[f.id] ?? 0})</span>
              </button>
            ))}
          </div>
          <div className="mb-4">
            <SearchInput value={query} onChange={setQuery} placeholder="Buscar por nombre, email o interés…" />
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
