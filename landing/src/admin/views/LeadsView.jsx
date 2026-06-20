import { useEffect, useState } from 'react'
import { UserPlus, RefreshCw, Mail, Phone, Flame, MessageCircle, Globe, Trash2 } from 'lucide-react'
import { listLeads, deleteLead } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDate,
} from '../ui'

function TypeBadge({ type }) {
  const t = (type || '').toUpperCase()
  const map = { CALIENTE: 'red', TIBIO: 'amber', FRIO: 'blue' }
  return <Badge tone={map[t] || 'gray'}>{t || '—'}</Badge>
}

// Canal de origen del lead: WhatsApp (verde) o Web (gris).
function ChannelBadge({ channel }) {
  if (channel === 'whatsapp') {
    return <Badge tone="green"><MessageCircle size={11} /> WhatsApp</Badge>
  }
  return <Badge tone="gray"><Globe size={11} /> Web</Badge>
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
    email: c.email,
    phone: c.phone,
    type: cl.lead_type,
    score: cl.interest_score,
    interest: ti.main_interest,
    status: md.status,
    channel: md.channel,
    created_at: md.created_at,
  }
}

export default function LeadsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

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
    } catch {
      window.alert('No se pudo eliminar el lead. Intentá de nuevo.')
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

  const columns = [
    { key: 'name', label: 'Nombre', render: (r) => <span className="font-medium text-ink">{r.name}</span> },
    { key: 'contact', label: 'Contacto', render: (r) => (
      <div className="space-y-0.5 text-xs text-slatey">
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}</p>}
        {!r.email && !r.phone && '—'}
      </div>
    ) },
    { key: 'interest', label: 'Interés', render: (r) => r.interest || '—' },
    { key: 'channel', label: 'Canal', render: (r) => <ChannelBadge channel={r.channel} /> },
    { key: 'type', label: 'Tipo', render: (r) => <TypeBadge type={r.type} /> },
    { key: 'score', label: 'Score', render: (r) => <ScoreBar score={r.score} /> },
    { key: 'created_at', label: 'Fecha', render: (r) => formatDate(r.created_at) },
    { key: 'actions', label: '', render: (r) => <DeleteButton r={r} /> },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-ink">{r.name}</span>
        <div className="flex items-center gap-1.5">
          <ChannelBadge channel={r.channel} />
          <TypeBadge type={r.type} />
        </div>
      </div>
      {r.interest && <p className="text-sm text-slatey">{r.interest}</p>}
      <div className="mt-2 space-y-0.5 text-xs text-slatey">
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}</p>}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <ScoreBar score={r.score} />
        <DeleteButton r={r} />
      </div>
    </div>
  )

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
        <ResponsiveTable columns={columns} rows={rows} renderCard={renderCard} />
      )}
    </div>
  )
}
