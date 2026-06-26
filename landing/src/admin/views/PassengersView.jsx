import { useEffect, useState } from 'react'
import {
  Users, RefreshCw, Phone, Mail, BedDouble, Trash2,
} from 'lucide-react'
import { listPassengers, deleteContact } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, OriginBadge, Loading, EmptyState, formatDate, WhatsAppDot,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import DetailDrawer from '../components/DetailDrawer'
import { useTableControls } from '../hooks/useTableControls'

function flatten(c) {
  const m = c.metrics || {}
  return {
    _key: c.id,
    id: c.id,
    name: c.full_name || [c.first_name, c.last_name].filter(Boolean).join(' ') || 'Sin nombre',
    email: c.email,
    phone: c.phone_number,
    whatsappLinked: c.whatsapp_linked,
    origin: c.origin,
    stays: m.purchases_made ?? 0,
    inHouse: !!c.is_staying_now,
    last: c.last_interaction_date,
  }
}

// Lee un contact_id del hash "#admin/pasajeros/{id}" (deep-link desde Reservas).
function contactIdFromHash() {
  const parts = window.location.hash.replace('#admin/', '').split('/')
  const id = parts[1] ? parseInt(parts[1], 10) : null
  return Number.isInteger(id) ? id : null
}

export default function PassengersView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(contactIdFromHash)
  const [onlyInHouse, setOnlyInHouse] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const load = () => {
    setLoading(true)
    listPassengers()
      .then((d) => setRows((Array.isArray(d) ? d : []).map(flatten)))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handleDelete = async (r) => {
    if (!window.confirm(`¿Eliminar a ${r.name}? Se quitará del listado de pasajeros (sus reservas quedan, pero sin vincular). Esta acción no se puede deshacer.`)) return
    setDeletingId(r.id)
    try {
      await deleteContact(r.id)
      setRows((prev) => prev.filter((x) => x.id !== r.id))
      toast.success(`${r.name} eliminado`)
    } catch {
      toast.error('No se pudo eliminar el pasajero. Intentá de nuevo.')
    } finally {
      setDeletingId(null)
    }
  }

  const DeleteButton = ({ r }) => (
    <button
      onClick={(e) => { e.stopPropagation(); handleDelete(r) }}
      disabled={deletingId === r.id}
      title="Eliminar pasajero"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
    >
      <Trash2 size={15} />
    </button>
  )

  // Soporta deep-link: si el hash trae un contact_id, abre su drawer.
  useEffect(() => {
    const onHash = () => setSelected(contactIdFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const closeDrawer = () => {
    setSelected(null)
    // Limpia el id del hash para no reabrir al volver.
    if (window.location.hash.startsWith('#admin/pasajeros/')) window.location.hash = 'admin/pasajeros'
  }

  const columns = [
    { key: 'name', label: 'Huésped', sortable: true, render: (r) => (
      <div className="flex items-center gap-2">
        <button onClick={() => setSelected(r.id)} className="font-medium text-hilton-700 hover:underline">{r.name}</button>
        {r.inHouse && <Badge tone="green"><BedDouble size={11} className="mr-1" /> En casa</Badge>}
      </div>
    ) },
    { key: 'contact', label: 'Contacto', render: (r) => (
      <div className="space-y-0.5 text-xs text-slatey">
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} title="Se comunicó por WhatsApp" /></p>}
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {!r.phone && !r.email && '—'}
      </div>
    ) },
    { key: 'origin', label: 'Origen', render: (r) => <OriginBadge origin={r.origin} /> },
    { key: 'stays', label: 'Estadías', sortable: true, render: (r) => <span className="tabular-nums font-medium text-ink">{r.stays}</span> },
    { key: 'last', label: 'Última actividad', sortable: true, render: (r) => formatDate(r.last) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1.5">
        <button onClick={() => setSelected(r.id)} className="text-xs font-medium text-hilton-600 hover:underline">Ver 360°</button>
        <DeleteButton r={r} />
      </div>
    ) },
  ]

  const renderCard = (r) => (
    <div className="relative">
      <button onClick={() => setSelected(r.id)} className="w-full text-left">
        <div className="mb-2 flex items-center justify-between pr-9">
          <span className="font-medium text-ink">{r.name}</span>
          <OriginBadge origin={r.origin} />
        </div>
        <div className="space-y-0.5 text-xs text-slatey">
          {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} title="Se comunicó por WhatsApp" /></p>}
          {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        </div>
        <p className="mt-2 text-xs text-slatey">
          <span className="tabular-nums font-medium text-ink">{r.stays}</span> estadía{r.stays === 1 ? '' : 's'}
        </p>
      </button>
      <div className="absolute right-0 top-0"><DeleteButton r={r} /></div>
    </div>
  )

  const inHouseCount = rows.filter((r) => r.inHouse).length
  const byHouse = onlyInHouse ? rows.filter((r) => r.inHouse) : rows
  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } =
    useTableControls(byHouse, {
      searchKeys: ['name', 'email', 'phone'],
      pageSize: 50,
      sortAccessors: {
        name: (r) => r.name || '',
        stays: (r) => r.stays || 0,
        last: (r) => r.last || '',
      },
    })

  return (
    <div>
      <PageHeader
        title="Huéspedes"
        subtitle="Huéspedes que reservaron al menos una vez. Tocá un nombre para ver su perfil 360°."
        right={
          <button onClick={load} className="btn-secondary px-4 py-2 text-xs">
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={Users} title="Aún no hay pasajeros"
                    desc="Cuando un huésped concrete una reserva, aparecerá acá con su historial." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={() => setOnlyInHouse(false)}
              className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${
                !onlyInHouse ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
              }`}
            >
              Todos <span className="tabular-nums opacity-70">({rows.length})</span>
            </button>
            <button
              onClick={() => setOnlyInHouse(true)}
              className={`flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-medium transition ${
                onlyInHouse ? 'bg-green-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
              }`}
            >
              <BedDouble size={13} /> Alojados ahora <span className="tabular-nums opacity-70">({inHouseCount})</span>
            </button>
          </div>
          <div className="mb-4">
            <SearchInput value={query} onChange={setQuery} placeholder="Buscar por nombre, email o teléfono…" />
          </div>
          {total === 0 ? (
            <EmptyState icon={BedDouble} title="Sin pasajeros en esta vista"
                        desc="Probá con otro filtro o búsqueda." />
          ) : (
            <>
              <ResponsiveTable columns={columns} rows={pageRows} renderCard={renderCard} sort={sort} onSort={toggleSort} />
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </>
      )}

      {selected && <DetailDrawer contactId={selected} onClose={closeDrawer} />}
    </div>
  )
}
