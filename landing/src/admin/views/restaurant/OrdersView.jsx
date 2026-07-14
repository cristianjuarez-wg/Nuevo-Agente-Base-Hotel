import { useState, useEffect } from 'react'
import { ClipboardList, RefreshCw, BedDouble, Store, ShoppingBag } from 'lucide-react'
import { listOrders, patchOrderStatus } from '../../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatUSD, formatARS, formatDate } from '../../ui'
import { toast } from '../../toast'
import SearchInput from '../../components/SearchInput'
import Pagination from '../../components/Pagination'
import { useTableControls } from '../../hooks/useTableControls'

const STATUS = [
  { id: 'all', label: 'Todos' },
  { id: 'pendiente', label: 'Pendientes' },
  { id: 'confirmado', label: 'Confirmados' },
  { id: 'en_preparacion', label: 'En preparación' },
  { id: 'entregado', label: 'Entregados' },
]
const STATUS_FLOW = ['pendiente', 'confirmado', 'en_preparacion', 'entregado']

function StatusBadge({ status }) {
  const map = {
    pendiente: 'amber', confirmado: 'blue', en_preparacion: 'blue',
    entregado: 'green', cancelado: 'red',
  }
  return <Badge tone={map[status] || 'gray'}>{(status || '').replace('_', ' ')}</Badge>
}

function FulfillmentBadge({ f }) {
  const map = {
    room_service: { icon: BedDouble, label: 'Habitación' },
    salon: { icon: Store, label: 'Salón' },
    retiro: { icon: ShoppingBag, label: 'Retiro' },
  }
  const m = map[f] || { icon: Store, label: f }
  const Icon = m.icon
  return <span className="inline-flex items-center gap-1 text-xs text-slatey"><Icon size={13} /> {m.label}</span>
}

export default function OrdersView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  const load = (silent = false) => {
    if (!silent) setLoading(true)
    listOrders().then((d) => setRows(Array.isArray(d) ? d : [])).catch(() => setRows([])).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const advance = async (o) => {
    const idx = STATUS_FLOW.indexOf(o.status)
    if (idx < 0 || idx >= STATUS_FLOW.length - 1) return
    const next = STATUS_FLOW[idx + 1]
    try { await patchOrderStatus(o.order_code, next); load(true); toast.success(`Pedido ${o.order_code}: ${next.replace('_', ' ')}`) }
    catch { toast.error('No se pudo actualizar') }
  }

  const byStatus = filter === 'all' ? rows : rows.filter((r) => r.status === filter)
  const counts = rows.reduce((a, r) => { a.all += 1; a[r.status] = (a[r.status] || 0) + 1; return a }, { all: 0 })

  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } = useTableControls(byStatus, {
    searchKeys: ['order_code', 'guest_name'],
    pageSize: 50,
    sortAccessors: { created_at: (r) => r.created_at || '', total: (r) => r.total_usd || 0 },
  })

  const columns = [
    { key: 'order_code', label: 'Pedido', render: (r) => <span className="font-semibold text-hilton-700">{r.order_code}</span> },
    { key: 'guest_name', label: 'Cliente', render: (r) => r.guest_name || '—' },
    { key: 'items', label: 'Detalle', render: (r) => (
      <div className="max-w-[220px] text-xs text-slatey">
        {(r.items || []).map((i, idx) => (
          <span key={idx}>
            {idx > 0 && ', '}{i.qty}× {i.name}
            {i.notes && <span className="text-amber-600"> ({i.notes})</span>}
          </span>
        ))}
        {r.notes && (
          <p className="mt-0.5 text-amber-700">📝 {r.notes}</p>
        )}
      </div>
    ) },
    { key: 'fulfillment', label: 'Destino', render: (r) => <FulfillmentBadge f={r.fulfillment} /> },
    { key: 'pay', label: 'Pago', render: (r) => <Badge tone={r.payment_mode === 'folio' ? 'hilton' : 'gray'}>{r.payment_mode === 'folio' ? 'A la habitación' : 'Link'}</Badge> },
    { key: 'total', label: 'Total', sortable: true, render: (r) => <span className="tabular-nums">{formatUSD(r.total_usd)} <span className="text-slatey">/ {formatARS(r.total_ars)}</span></span> },
    { key: 'created_at', label: 'Fecha', sortable: true, render: (r) => formatDate(r.created_at) },
    { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'actions', label: '', render: (r) => (
      STATUS_FLOW.indexOf(r.status) >= 0 && STATUS_FLOW.indexOf(r.status) < STATUS_FLOW.length - 1
        ? <button onClick={() => advance(r)} className="rounded-lg border border-hilton-200 px-2.5 py-1 text-xs font-medium text-hilton-700 transition hover:bg-hilton-50">Avanzar →</button>
        : null
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.order_code}</span>
        <StatusBadge status={r.status} />
      </div>
      <p className="font-medium text-ink">{r.guest_name || '—'}</p>
      <p className="mt-1 text-xs text-slatey">
        {(r.items || []).map((i, idx) => (
          <span key={idx}>
            {idx > 0 && ', '}{i.qty}× {i.name}
            {i.notes && <span className="text-amber-600"> ({i.notes})</span>}
          </span>
        ))}
      </p>
      {r.notes && <p className="mt-1 text-xs text-amber-700">📝 {r.notes}</p>}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold tabular-nums text-hilton-700">{formatUSD(r.total_usd)}</span>
        <FulfillmentBadge f={r.fulfillment} />
      </div>
    </div>
  )

  if (loading) return <Loading label="Cargando pedidos…" />

  return (
    <div>
      <PageHeader title="Pedidos del restaurante" subtitle="Comandas tomadas por el agente o desde la web. Avanzá el estado para cocina y mozos." right={<button onClick={() => load()} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>} />
      {rows.length === 0 ? (
        <EmptyState icon={ClipboardList} title="Aún no hay pedidos" desc="Los pedidos del restaurante aparecerán acá." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {STATUS.map((f) => (
              <button key={f.id} onClick={() => setFilter(f.id)} className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${filter === f.id ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'}`}>
                {f.label} <span className="tabular-nums opacity-70">({counts[f.id] ?? 0})</span>
              </button>
            ))}
          </div>
          <div className="mb-4"><SearchInput value={query} onChange={setQuery} placeholder="Buscar por código o cliente…" /></div>
          {total === 0 ? (
            <EmptyState icon={ClipboardList} title="Sin pedidos en esta vista" desc="Probá con otro filtro." />
          ) : (
            <>
              <ResponsiveTable columns={columns} rows={pageRows.map((r) => ({ ...r, _key: r.order_code }))} renderCard={renderCard} sort={sort} onSort={toggleSort} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
