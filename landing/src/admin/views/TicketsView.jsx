import { useEffect, useState } from 'react'
import {
  LifeBuoy, RefreshCw, CheckCircle2, Trash2,
  Check, RotateCcw, Loader2, User,
} from 'lucide-react'
import {
  listTickets, deleteTicket, preResolveTicket, resolveTicketAdmin, reopenTicket,
} from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDate,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import { useTableControls } from '../hooks/useTableControls'

const STATUS_FILTERS = [
  { id: 'all', label: 'Todos' },
  { id: 'asignado', label: 'Asignados' },
  { id: 'pre_resuelto', label: 'Pre-resueltos' },
  { id: 'resuelto', label: 'Resueltos' },
  { id: 'open', label: 'Abiertos' },
  { id: 'escalated', label: 'Escalados' },
]

function StatusBadge({ status }) {
  const map = {
    // Ciclo operativo (Fase 4)
    asignado: { tone: 'blue', label: 'Asignado' },
    pre_resuelto: { tone: 'amber', label: 'Pre-resuelto' },
    resuelto: { tone: 'green', label: 'Resuelto' },
    // Estados base
    resolved: { tone: 'green', label: 'Resuelto' },
    escalated: { tone: 'red', label: 'Escalado' },
    open: { tone: 'amber', label: 'Abierto' },
    in_progress: { tone: 'blue', label: 'En curso' },
  }
  const s = map[status] || { tone: 'gray', label: status }
  return <Badge tone={s.tone}>{s.label}</Badge>
}

const AREA_LABELS = {
  mantenimiento: 'Mantenimiento', recepcion: 'Recepción',
  housekeeping: 'Housekeeping', general: 'General',
}

function AreaBadge({ area }) {
  if (!area) return <span className="text-xs text-slatey">—</span>
  return <Badge tone="gray">{AREA_LABELS[area] || area}</Badge>
}

function OriginBadge({ origin }) {
  return origin === 'staff'
    ? <Badge tone="hilton"><User size={11} className="mr-1" /> Equipo</Badge>
    : <Badge tone="gray">Huésped</Badge>
}

function CategoryBadge({ category }) {
  const map = {
    info: 'Información', change: 'Cambio', cancel: 'Cancelación',
    complaint: 'Reclamo', general: 'General', restaurant: 'Restaurante',
    service_request: 'Servicio',
  }
  const tone = category === 'restaurant' ? 'hilton' : category === 'service_request' ? 'blue' : 'gray'
  return <Badge tone={tone}>{map[category] || category}</Badge>
}

// Estados del ciclo operativo donde tienen sentido las acciones manuales (fallback humano).
const OPERATIONAL = new Set(['asignado', 'pre_resuelto', 'resuelto', 'open', 'in_progress'])

export default function TicketsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [filter, setFilter] = useState('all')

  const load = () => {
    setLoading(true)
    listTickets()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handleDelete = async (r) => {
    if (!window.confirm(`¿Eliminar el ticket ${r.ticket_number}? Esta acción no se puede deshacer.`)) return
    setDeletingId(r.id)
    try {
      await deleteTicket(r.id)
      setRows((prev) => prev.filter((x) => x.id !== r.id))
      toast.success(`Ticket ${r.ticket_number} eliminado`)
    } catch {
      toast.error('No se pudo eliminar el ticket. Intentá de nuevo.')
    } finally {
      setDeletingId(null)
    }
  }

  // Acciones operativas manuales (fallback humano si el equipo no usa WhatsApp).
  const runAction = async (r, fn, okMsg) => {
    setBusyId(r.id)
    try {
      const updated = await fn(r.id)
      setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, ...updated } : x)))
      toast.success(okMsg)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo actualizar el ticket')
    } finally {
      setBusyId(null)
    }
  }

  const DeleteButton = ({ r }) => (
    <button
      onClick={() => handleDelete(r)}
      disabled={deletingId === r.id}
      title="Eliminar ticket"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
    >
      <Trash2 size={15} />
    </button>
  )

  // Botones de transición según el estado actual del ticket operativo.
  const OpsActions = ({ r }) => {
    if (!OPERATIONAL.has(r.status)) return null
    const busy = busyId === r.id
    const Btn = ({ onClick, icon: Icon, label, tone = 'forest' }) => (
      <button onClick={onClick} disabled={busy} title={label}
        className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium transition disabled:opacity-50 ${
          tone === 'amber' ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
          : tone === 'slate' ? 'border-hilton-200 text-slatey hover:bg-hilton-50'
          : 'border-forest-200 text-forest-700 hover:bg-forest-50'}`}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />} {label}
      </button>
    )
    return (
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {(r.status === 'asignado' || r.status === 'open' || r.status === 'in_progress') && (
          <Btn onClick={() => runAction(r, (id) => preResolveTicket(id, 'Resuelto por el equipo'), `${r.ticket_number} pre-resuelto`)}
               icon={Check} label="Pre-resolver" tone="amber" />
        )}
        {r.status === 'pre_resuelto' && (
          <Btn onClick={() => runAction(r, resolveTicketAdmin, `${r.ticket_number} resuelto`)} icon={CheckCircle2} label="Resolver" />
        )}
        {r.status === 'resuelto' && (
          <Btn onClick={() => runAction(r, reopenTicket, `${r.ticket_number} reabierto`)} icon={RotateCcw} label="Reabrir" tone="slate" />
        )}
      </div>
    )
  }

  const columns = [
    { key: 'ticket_number', label: 'Ticket', render: (r) => <span className="font-semibold text-hilton-700">{r.ticket_number}</span> },
    { key: 'guest_name', label: 'Huésped / origen', render: (r) => (
      <div>
        <p className="font-medium text-ink">{r.guest_name || (r.origin === 'staff' ? 'Tarea interna' : '—')}</p>
        <p className="text-xs text-slatey">{r.booking_code || (r.room_number ? `Hab. ${r.room_number}` : '')}</p>
      </div>
    ) },
    { key: 'subject', label: 'Asunto', render: (r) => <span className="text-sm">{r.subject}</span> },
    { key: 'area', label: 'Área', render: (r) => <AreaBadge area={r.assigned_area} /> },
    { key: 'assigned', label: 'Asignado a', render: (r) => (
      r.assigned_staff_name
        ? <span className="text-sm text-ink">{r.assigned_staff_name}</span>
        : <span className="text-xs text-slatey">— sin asignar</span>
    ) },
    { key: 'origin', label: 'Origen', render: (r) => <OriginBadge origin={r.origin} /> },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'created_at', label: 'Fecha', sortable: true, render: (r) => formatDate(r.created_at) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1.5"><OpsActions r={r} /><DeleteButton r={r} /></div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.ticket_number}</span>
        <StatusBadge status={r.status} />
      </div>
      <p className="font-medium text-ink">
        {r.guest_name || (r.origin === 'staff' ? 'Tarea interna' : '—')}
        {(r.booking_code || r.room_number) && (
          <span className="text-xs font-normal text-slatey"> · {r.booking_code || `Hab. ${r.room_number}`}</span>
        )}
      </p>
      <p className="mt-1 text-sm text-slatey">{r.subject}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <AreaBadge area={r.assigned_area} />
        <OriginBadge origin={r.origin} />
        {r.assigned_staff_name && <span className="text-xs text-slatey">→ {r.assigned_staff_name}</span>}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <OpsActions r={r} />
        <DeleteButton r={r} />
      </div>
    </div>
  )

  // Chips por estado → búsqueda + orden + paginación.
  const byStatus = filter === 'all' ? rows : rows.filter((r) => r.status === filter)
  const counts = rows.reduce((acc, r) => { acc.all += 1; acc[r.status] = (acc[r.status] || 0) + 1; return acc }, { all: 0 })
  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } =
    useTableControls(byStatus, {
      searchKeys: ['ticket_number', 'guest_name', 'subject', 'booking_code'],
      pageSize: 50,
      sortAccessors: { created_at: (r) => r.created_at || '' },
    })

  return (
    <div>
      <PageHeader
        title="Soporte / Operaciones"
        subtitle="Consultas y pedidos atendidos por el agente. Los pedidos de servicio se asignan al equipo por área y se cierran con validación del huésped."
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
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {STATUS_FILTERS.map((f) => (
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
            <SearchInput value={query} onChange={setQuery} placeholder="Buscar por ticket, huésped o asunto…" />
          </div>
          {total === 0 ? (
            <EmptyState icon={LifeBuoy} title="Sin tickets en esta vista" desc="Probá con otro filtro o búsqueda." />
          ) : (
            <>
              <ResponsiveTable
                columns={columns}
                rows={pageRows.map((r) => ({ ...r, _key: r.ticket_number }))}
                renderCard={renderCard}
                sort={sort}
                onSort={toggleSort}
              />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
