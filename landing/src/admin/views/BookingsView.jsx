import { useEffect, useState } from 'react'
import { CalendarCheck, RefreshCw, BedDouble, Clock, CheckCircle2, Trash2, MessageSquare, X } from 'lucide-react'
import { listBookings, deleteBooking } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, OriginBadge, Loading, EmptyState, formatUSD, formatARS, formatDate,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import ChatTranscript from '../components/ChatTranscript'
import { useTableControls } from '../hooks/useTableControls'

// Estado temporal de la estadía (derivado en el backend como stay_status).
function StayBadge({ stay }) {
  const map = {
    checked_in: { tone: 'green', icon: BedDouble, label: 'En casa' },
    upcoming: { tone: 'blue', icon: Clock, label: 'Próxima' },
    past: { tone: 'gray', icon: CheckCircle2, label: 'Finalizada' },
    cancelled: { tone: 'red', icon: null, label: 'Cancelada' },
  }
  const s = map[stay] || map.upcoming
  const Icon = s.icon
  return <Badge tone={s.tone}>{Icon && <Icon size={11} className="mr-1" />}{s.label}</Badge>
}

const FILTERS = [
  { id: 'all', label: 'Todas' },
  { id: 'checked_in', label: 'Alojados hoy' },
  { id: 'upcoming', label: 'Próximas' },
  { id: 'past', label: 'Finalizadas' },
]

function FilterChips({ value, counts, onChange }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Filtrar reservas">
      {FILTERS.map((f) => {
        const active = value === f.id
        const n = counts[f.id] ?? 0
        return (
          <button
            key={f.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(f.id)}
            className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${
              active ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
            }`}
          >
            {f.label} <span className="tabular-nums opacity-70">({n})</span>
          </button>
        )
      })}
    </div>
  )
}

export default function BookingsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [deletingCode, setDeletingCode] = useState(null)
  const [chatBooking, setChatBooking] = useState(null)  // reserva cuya conversación se está viendo

  const load = () => {
    setLoading(true)
    listBookings()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handleDelete = async (r) => {
    if (!window.confirm(`¿Eliminar la reserva ${r.code} de ${r.guest_name}? Esta acción no se puede deshacer.`)) return
    setDeletingCode(r.code)
    try {
      await deleteBooking(r.code)
      setRows((prev) => prev.filter((x) => x.code !== r.code))
      toast.success(`Reserva ${r.code} eliminada`)
    } catch {
      toast.error('No se pudo eliminar la reserva. Intentá de nuevo.')
    } finally {
      setDeletingCode(null)
    }
  }

  const DeleteButton = ({ r }) => (
    <button
      onClick={() => handleDelete(r)}
      disabled={deletingCode === r.code}
      title="Eliminar reserva"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
    >
      <Trash2 size={15} />
    </button>
  )

  const ChatButton = ({ r }) => (
    <button
      onClick={() => setChatBooking(r)}
      title="Ver conversación"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-hilton-50 hover:text-hilton-700"
    >
      <MessageSquare size={15} />
    </button>
  )

  // Abre el perfil 360° del pasajero (deep-link manejado por PassengersView).
  const goToProfile = (contactId) => {
    window.location.hash = `admin/pasajeros/${contactId}`
  }

  const counts = rows.reduce(
    (acc, r) => {
      acc.all += 1
      acc[r.stay_status] = (acc[r.stay_status] || 0) + 1
      return acc
    },
    { all: 0 }
  )

  // Chips de estado (filtro previo) → luego búsqueda + orden + paginación (hook).
  const byStatus = filter === 'all' ? rows : rows.filter((r) => r.stay_status === filter)
  // Orden por defecto: "alojados hoy" primero, luego check-in descendente.
  const baseSorted = byStatus.slice().sort((a, b) => {
    if (a.stay_status === 'checked_in' && b.stay_status !== 'checked_in') return -1
    if (b.stay_status === 'checked_in' && a.stay_status !== 'checked_in') return 1
    return (b.check_in || '').localeCompare(a.check_in || '')
  })
  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } =
    useTableControls(baseSorted, {
      searchKeys: ['code', 'guest_name', 'room_type'],
      pageSize: 50,
      sortAccessors: {
        check_in: (r) => r.check_in || '',
        total: (r) => r.total_price_usd || 0,
      },
    })

  const GuestName = ({ r }) =>
    r.contact_id ? (
      <button onClick={() => goToProfile(r.contact_id)} className="font-medium text-hilton-700 hover:underline">
        {r.guest_name}
      </button>
    ) : (
      <span className="font-medium text-ink">{r.guest_name}</span>
    )

  const columns = [
    { key: 'code', label: 'Código', render: (r) => <span className="font-semibold text-hilton-700">{r.code}</span> },
    { key: 'guest_name', label: 'Huésped', render: (r) => <GuestName r={r} /> },
    { key: 'room_type', label: 'Habitación', render: (r) => (
      <span>
        {r.room_type}
        {r.room_number && <span className="ml-1.5 rounded bg-hilton-50 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-hilton-700">N° {r.room_number}</span>}
      </span>
    ) },
    { key: 'stay', label: 'Estadía', sortable: true, sortKey: 'check_in', render: (r) => `${formatDate(r.check_in)} → ${formatDate(r.check_out)}` },
    { key: 'stay_status', label: 'Situación', render: (r) => <StayBadge stay={r.stay_status} /> },
    { key: 'total', label: 'Total', sortable: true, render: (r) => (
      <span className="tabular-nums">{formatUSD(r.total_price_usd)} <span className="text-slatey">/ {formatARS(r.total_price_ars)}</span></span>
    ) },
    { key: 'origin', label: 'Origen', render: (r) => <OriginBadge origin={r.origin} /> },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1"><ChatButton r={r} /><DeleteButton r={r} /></div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.code}</span>
        <StayBadge stay={r.stay_status} />
      </div>
      <GuestName r={r} />
      <p className="text-sm text-slatey">
        {r.room_type}
        {r.room_number && <span className="ml-1.5 font-semibold tabular-nums text-hilton-700">· N° {r.room_number}</span>}
      </p>
      <p className="mt-1 text-xs text-slatey">{formatDate(r.check_in)} → {formatDate(r.check_out)} · {r.nights} noche(s)</p>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold tabular-nums text-hilton-700">{formatUSD(r.total_price_usd)}</span>
        <div className="flex items-center gap-1.5">
          <OriginBadge origin={r.origin} />
          <ChatButton r={r} />
          <DeleteButton r={r} />
        </div>
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
        <>
          <FilterChips value={filter} counts={counts} onChange={setFilter} />
          <div className="mb-4">
            <SearchInput value={query} onChange={setQuery} placeholder="Buscar por código, huésped o habitación…" />
          </div>
          {total === 0 ? (
            <EmptyState icon={CalendarCheck} title="Sin reservas en esta vista" desc="Probá con otro filtro o búsqueda." />
          ) : (
            <>
              <ResponsiveTable
                columns={columns}
                rows={pageRows.map((r) => ({ ...r, _key: r.code }))}
                renderCard={renderCard}
                sort={sort}
                onSort={toggleSort}
              />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {chatBooking && (
        <BookingChatDrawer booking={chatBooking} onClose={() => setChatBooking(null)} />
      )}
    </div>
  )
}

// Panel lateral con la conversación que originó una reserva (por session_id).
function BookingChatDrawer({ booking, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-card-lg animate-slide-up">
        <div className="flex items-start justify-between border-b border-mist px-5 py-4">
          <div className="min-w-0">
            <p className="font-serif text-lg font-700 text-hilton-700">{booking.code}</p>
            <p className="mt-0.5 text-sm text-slatey">{booking.guest_name} · {booking.room_type}</p>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ChatTranscript sessionId={booking.session_id} />
        </div>
      </aside>
    </div>
  )
}

function StatusBadge({ status }) {
  const map = { confirmed: 'green', cancelled: 'red', completed: 'blue', pending: 'amber' }
  return <Badge tone={map[status] || 'gray'}>{status}</Badge>
}
