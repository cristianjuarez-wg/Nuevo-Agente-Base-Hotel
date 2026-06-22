import { useState, useEffect } from 'react'
import { Ticket, RefreshCw, Check, Loader2 } from 'lucide-react'
import { listVouchers, redeemVoucher } from '../../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatUSD, formatARS, formatDate } from '../../ui'
import { toast } from '../../toast'
import SearchInput from '../../components/SearchInput'
import Pagination from '../../components/Pagination'
import { useTableControls } from '../../hooks/useTableControls'

const FILTERS = [
  { id: 'emitido', label: 'Emitidos' },
  { id: 'canjeado', label: 'Canjeados' },
  { id: 'all', label: 'Todos' },
]

function StatusBadge({ status }) {
  const map = { emitido: 'blue', canjeado: 'green', cancelado: 'gray' }
  const label = { emitido: 'Emitido', canjeado: 'Canjeado', cancelado: 'Cancelado' }
  return <Badge tone={map[status] || 'gray'}>{label[status] || status}</Badge>
}

export default function VouchersView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('emitido')
  const [redeemingId, setRedeemingId] = useState(null)

  const load = (f = filter, silent = false) => {
    if (!silent) setLoading(true)
    listVouchers(f === 'all' ? undefined : f)
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load(filter) }, [filter])

  const redeem = async (v) => {
    if (!window.confirm(`¿Canjear el voucher ${v.code} de ${v.buyer_name || 'visitante'}? Esta acción no se puede deshacer.`)) return
    setRedeemingId(v.id)
    try {
      await redeemVoucher(v.code)
      load(filter, true)
      toast.success(`Voucher ${v.code} canjeado`)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo canjear el voucher')
    } finally {
      setRedeemingId(null)
    }
  }

  const itemsTxt = (v) => (v.items || []).map((i) => `${i.qty}× ${i.name}`).join(', ')

  const RedeemBtn = ({ v }) => (
    v.status === 'emitido' ? (
      <button onClick={() => redeem(v)} disabled={redeemingId === v.id}
        className="inline-flex items-center gap-1 rounded-lg border border-forest-200 px-2.5 py-1 text-xs font-medium text-forest-700 transition hover:bg-forest-50 disabled:opacity-50">
        {redeemingId === v.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Canjear
      </button>
    ) : v.redeemed_at ? <span className="text-xs text-slatey tabular-nums">{formatDate(v.redeemed_at)}</span> : null
  )

  const columns = [
    { key: 'code', label: 'Voucher', render: (v) => <span className="font-semibold text-hilton-700">{v.code}</span> },
    { key: 'buyer_name', label: 'Comprador', render: (v) => v.buyer_name || '—' },
    { key: 'items', label: 'Incluye', render: (v) => <span className="text-xs text-slatey">{itemsTxt(v)}</span> },
    { key: 'total', label: 'Total', render: (v) => <span className="tabular-nums">{formatUSD(v.total_usd)} <span className="text-slatey">/ {formatARS(v.total_ars)}</span></span> },
    { key: 'created_at', label: 'Emitido', render: (v) => formatDate(v.created_at) },
    { key: 'status', label: 'Estado', render: (v) => <StatusBadge status={v.status} /> },
    { key: 'actions', label: '', render: (v) => <div className="flex justify-end"><RedeemBtn v={v} /></div> },
  ]

  const renderCard = (v) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{v.code}</span>
        <StatusBadge status={v.status} />
      </div>
      <p className="font-medium text-ink">{v.buyer_name || '—'}</p>
      <p className="mt-1 text-xs text-slatey">{itemsTxt(v)}</p>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm font-semibold tabular-nums text-hilton-700">{formatUSD(v.total_usd)}</span>
        <RedeemBtn v={v} />
      </div>
    </div>
  )

  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } = useTableControls(rows, {
    searchKeys: ['code', 'buyer_name'],
    pageSize: 50,
  })

  return (
    <div>
      <PageHeader title="Vouchers" subtitle="Compras anticipadas de visitantes. Buscá el código y canjealo cuando lleguen." right={<button onClick={() => load(filter)} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>} />
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)} className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${filter === f.id ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'}`}>{f.label}</button>
        ))}
      </div>
      {loading ? (
        <Loading label="Cargando vouchers…" />
      ) : rows.length === 0 ? (
        <EmptyState icon={Ticket} title="Sin vouchers" desc="Los vouchers que emita el agente aparecerán acá para canjear." />
      ) : (
        <>
          <div className="mb-4"><SearchInput value={query} onChange={setQuery} placeholder="Buscar por código o comprador…" /></div>
          {total === 0 ? (
            <EmptyState icon={Ticket} title="Sin vouchers en esta vista" desc="Probá con otro filtro." />
          ) : (
            <>
              <ResponsiveTable columns={columns} rows={pageRows.map((v) => ({ ...v, _key: v.code }))} renderCard={renderCard} sort={sort} onSort={toggleSort} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  )
}
