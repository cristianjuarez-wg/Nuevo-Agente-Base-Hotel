import { useEffect, useState } from 'react'
import { LifeBuoy, RefreshCw, Bot, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { listTickets } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDate,
} from '../ui'

function StatusBadge({ status }) {
  const map = {
    resolved: { tone: 'green', label: 'Resuelto' },
    escalated: { tone: 'red', label: 'Escalado' },
    open: { tone: 'amber', label: 'Abierto' },
    in_progress: { tone: 'blue', label: 'En curso' },
  }
  const s = map[status] || { tone: 'gray', label: status }
  return <Badge tone={s.tone}>{s.label}</Badge>
}

function CategoryBadge({ category }) {
  const map = {
    info: 'Información', change: 'Cambio', cancel: 'Cancelación',
    complaint: 'Reclamo', general: 'General',
  }
  return <Badge tone="gray">{map[category] || category}</Badge>
}

export default function TicketsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    listTickets()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const columns = [
    { key: 'ticket_number', label: 'Ticket', render: (r) => <span className="font-semibold text-hilton-700">{r.ticket_number}</span> },
    { key: 'guest_name', label: 'Huésped', render: (r) => (
      <div>
        <p className="font-medium text-ink">{r.guest_name || '—'}</p>
        <p className="text-xs text-slatey">{r.booking_code}</p>
      </div>
    ) },
    { key: 'subject', label: 'Asunto', render: (r) => <span className="text-sm">{r.subject}</span> },
    { key: 'category', label: 'Categoría', render: (r) => <CategoryBadge category={r.category} /> },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'resolution', label: 'Resolución', render: (r) => r.escalated ? (
      <span className="inline-flex items-center gap-1 text-xs text-red-600"><AlertTriangle size={13} /> A asesor</span>
    ) : (
      <span className="inline-flex items-center gap-1 text-xs text-green-600"><Bot size={13} /> Auto (IA)</span>
    ) },
    { key: 'created_at', label: 'Fecha', render: (r) => formatDate(r.created_at) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.ticket_number}</span>
        <StatusBadge status={r.status} />
      </div>
      <p className="font-medium text-ink">{r.guest_name} <span className="text-xs font-normal text-slatey">· {r.booking_code}</span></p>
      <p className="mt-1 text-sm text-slatey">{r.subject}</p>
      <div className="mt-2 flex items-center justify-between">
        <CategoryBadge category={r.category} />
        {r.escalated ? (
          <span className="inline-flex items-center gap-1 text-xs text-red-600"><AlertTriangle size={13} /> A asesor</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-green-600"><CheckCircle2 size={13} /> Auto (IA)</span>
        )}
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Soporte / Tickets"
        subtitle="Consultas post-reserva atendidas por el agente. Las que requieren acción humana quedan escaladas."
        right={
          <button onClick={load} className="btn-secondary px-4 py-2 text-xs">
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={LifeBuoy} title="Aún no hay tickets" desc="Cuando un huésped contacte al agente con su código de reserva, se abrirá un ticket." />
      ) : (
        <ResponsiveTable columns={columns} rows={rows.map((r) => ({ ...r, _key: r.ticket_number }))} renderCard={renderCard} />
      )}
    </div>
  )
}
