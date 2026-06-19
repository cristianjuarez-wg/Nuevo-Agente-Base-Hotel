import { useEffect, useState } from 'react'
import { CalendarCheck, Globe, Bot, RefreshCw } from 'lucide-react'
import { listBookings } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatARS, formatDate,
} from '../ui'

function SourceBadge({ source }) {
  return source === 'agente' ? (
    <Badge tone="blue">
      <Bot size={12} className="mr-1" /> Agente
    </Badge>
  ) : (
    <Badge tone="gray">
      <Globe size={12} className="mr-1" /> Web
    </Badge>
  )
}

function StatusBadge({ status }) {
  const map = { confirmed: 'green', cancelled: 'red', completed: 'blue', pending: 'amber' }
  return <Badge tone={map[status] || 'gray'}>{status}</Badge>
}

export default function BookingsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    listBookings()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const columns = [
    { key: 'code', label: 'Código', render: (r) => <span className="font-semibold text-hilton-700">{r.code}</span> },
    { key: 'guest_name', label: 'Huésped' },
    { key: 'room_type', label: 'Habitación' },
    { key: 'stay', label: 'Estadía', render: (r) => `${formatDate(r.check_in)} → ${formatDate(r.check_out)}` },
    { key: 'total', label: 'Total', render: (r) => (
      <span className="tabular-nums">USD {r.total_price_usd} <span className="text-slatey">/ ARS {formatARS(r.total_price_ars)}</span></span>
    ) },
    { key: 'source', label: 'Origen', render: (r) => <SourceBadge source={r.source} /> },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.code}</span>
        <SourceBadge source={r.source} />
      </div>
      <p className="font-medium text-ink">{r.guest_name}</p>
      <p className="text-sm text-slatey">{r.room_type}</p>
      <p className="mt-1 text-xs text-slatey">{formatDate(r.check_in)} → {formatDate(r.check_out)} · {r.nights} noche(s)</p>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold tabular-nums text-hilton-700">USD {r.total_price_usd}</span>
        <StatusBadge status={r.status} />
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Reservas"
        subtitle="Todas las reservas, desde la web y desde el agente."
        right={
          <button onClick={load} className="btn-secondary px-4 py-2 text-xs">
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={CalendarCheck} title="Aún no hay reservas" desc="Las reservas web y del agente aparecerán acá." />
      ) : (
        <ResponsiveTable columns={columns} rows={rows.map((r) => ({ ...r, _key: r.code }))} renderCard={renderCard} />
      )}
    </div>
  )
}
