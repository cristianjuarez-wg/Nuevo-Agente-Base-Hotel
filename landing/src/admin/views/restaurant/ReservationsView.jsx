import { useState, useEffect } from 'react'
import { CalendarClock, RefreshCw, Users, BedDouble, Store, Check, X, Sparkles } from 'lucide-react'
import { listTableReservations, patchTableReservationStatus } from '../../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDateTime } from '../../ui'
import { toast } from '../../toast'
import SearchInput from '../../components/SearchInput'
import Pagination from '../../components/Pagination'
import { useTableControls } from '../../hooks/useTableControls'

const SCOPES = [
  { id: 'upcoming', label: 'Próximas' },
  { id: 'today', label: 'Hoy' },
  { id: 'week', label: 'Esta semana' },
  { id: 'all', label: 'Todas' },
]

function StatusBadge({ status }) {
  const map = { confirmada: 'blue', sentada: 'green', no_show: 'red', cancelada: 'gray' }
  const label = { confirmada: 'Confirmada', sentada: 'Sentada', no_show: 'No-show', cancelada: 'Cancelada' }
  return <Badge tone={map[status] || 'gray'}>{label[status] || status}</Badge>
}

export default function ReservationsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [scope, setScope] = useState('upcoming')

  const load = (sc = scope, silent = false) => {
    if (!silent) setLoading(true)
    listTableReservations(sc === 'all' ? undefined : sc)
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load(scope) }, [scope])

  const setStatus = async (r, status) => {
    try {
      await patchTableReservationStatus(r.code, status)
      load(scope, true)
      toast.success(`${r.code}: ${status.replace('_', '-')}`)
    } catch { toast.error('No se pudo actualizar') }
  }

  const OriginCell = ({ r }) => (
    r.is_guest
      ? <span className="inline-flex items-center gap-1 text-xs text-hilton-700"><BedDouble size={13} /> Huésped</span>
      : <span className="inline-flex items-center gap-1 text-xs text-slatey"><Store size={13} /> Visitante</span>
  )

  const Actions = ({ r }) => {
    if (r.status === 'cancelada' || r.status === 'no_show' || r.status === 'sentada') return null
    return (
      <div className="flex items-center justify-end gap-1.5">
        <button onClick={() => setStatus(r, 'sentada')} title="Marcar sentada"
          className="inline-flex items-center gap-1 rounded-lg border border-forest-200 px-2 py-1 text-xs font-medium text-forest-700 transition hover:bg-forest-50"><Check size={13} /> Sentada</button>
        <button onClick={() => setStatus(r, 'no_show')} title="No-show"
          className="rounded-lg border border-red-200 px-2 py-1 text-xs font-medium text-red-600 transition hover:bg-red-50">No-show</button>
        <button onClick={() => setStatus(r, 'cancelada')} title="Cancelar"
          className="inline-flex items-center justify-center rounded-lg p-1 text-slatey transition hover:bg-mist hover:text-ink"><X size={14} /></button>
      </div>
    )
  }

  const columns = [
    { key: 'reserved_for', label: 'Fecha y hora', render: (r) => <span className="font-medium tabular-nums text-ink">{formatDateTime(r.reserved_for)}</span> },
    { key: 'guest_name', label: 'A nombre de', render: (r) => r.guest_name || '—' },
    { key: 'party_size', label: 'Personas', render: (r) => <span className="inline-flex items-center gap-1 tabular-nums text-ink"><Users size={13} className="text-slatey" /> {r.party_size}</span> },
    { key: 'origin', label: 'Origen', render: (r) => <OriginCell r={r} /> },
    { key: 'notes', label: 'Pedido especial', render: (r) => (
      r.notes
        ? <span className="inline-flex items-center gap-1 text-xs text-amber-700"><Sparkles size={13} className="shrink-0" /> {r.notes}</span>
        : <span className="text-xs text-slatey">—</span>
    ) },
    { key: 'code', label: 'Código', render: (r) => <span className="font-semibold text-hilton-700">{r.code}</span> },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'actions', label: '', render: (r) => <Actions r={r} /> },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium tabular-nums text-ink">{formatDateTime(r.reserved_for)}</span>
        <StatusBadge status={r.status} />
      </div>
      <p className="font-medium text-ink">{r.guest_name || '—'}</p>
      <div className="mt-1 flex items-center gap-3 text-xs text-slatey">
        <span className="inline-flex items-center gap-1"><Users size={12} /> {r.party_size}</span>
        <OriginCell r={r} />
        <span className="font-semibold text-hilton-700">{r.code}</span>
      </div>
      {r.notes && (
        <p className="mt-1.5 inline-flex items-start gap-1 text-xs text-amber-700"><Sparkles size={13} className="mt-0.5 shrink-0" /> {r.notes}</p>
      )}
      <div className="mt-2"><Actions r={r} /></div>
    </div>
  )

  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } = useTableControls(rows, {
    searchKeys: ['code', 'guest_name'],
    pageSize: 50,
  })

  return (
    <div>
      <PageHeader title="Reservas de mesa" subtitle="Agenda del restaurante, ordenada del próximo turno al más lejano." right={<button onClick={() => load(scope)} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>} />
      <div className="mb-4 flex flex-wrap gap-2">
        {SCOPES.map((s) => (
          <button key={s.id} onClick={() => setScope(s.id)} className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${scope === s.id ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'}`}>{s.label}</button>
        ))}
      </div>
      {loading ? (
        <Loading label="Cargando agenda…" />
      ) : rows.length === 0 ? (
        <EmptyState icon={CalendarClock} title="Sin reservas de mesa" desc="Las reservas que tome el agente o la web aparecerán acá." />
      ) : (
        <>
          <div className="mb-4"><SearchInput value={query} onChange={setQuery} placeholder="Buscar por código o nombre…" /></div>
          {total === 0 ? (
            <EmptyState icon={CalendarClock} title="Sin reservas en esta vista" desc="Probá con otro filtro." />
          ) : (
            <>
              <ResponsiveTable columns={columns} rows={pageRows.map((r) => ({ ...r, _key: r.code }))} renderCard={renderCard} sort={sort} onSort={toggleSort} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
