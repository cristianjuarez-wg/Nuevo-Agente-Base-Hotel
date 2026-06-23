import { useEffect, useState } from 'react'
import {
  LifeBuoy, RefreshCw, CheckCircle2, Trash2,
  Check, RotateCcw, Loader2, User, Bot, Hand, ChevronRight, SlidersHorizontal,
} from 'lucide-react'
import {
  listTickets, deleteTicket, preResolveTicket, resolveTicketAdmin, reopenTicket,
  assignTicket, setTicketPriority, listStaff,
} from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, Loading, EmptyState, formatDate,
} from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import ChatTranscript from '../components/ChatTranscript'
import { useTableControls } from '../hooks/useTableControls'

// Dos flujos distintos conviven en la misma tabla: OPERACIONES (pedidos de servicio que se
// asignan al equipo) y CONSULTAS (post-venta informativa que el agente responde o escala).
// El toggle los separa; cada uno trae sus propios filtros de estado.
const WORKFLOWS = [
  { id: 'operaciones', label: 'Operaciones', cats: ['service_request', 'general', 'restaurant', 'table_reservation', 'voucher'] },
  { id: 'consultas', label: 'Consultas', cats: ['info', 'change', 'cancel', 'complaint'] },
]

// Estados por flujo. Operaciones usa el ciclo nuevo; Consultas el clásico de post-venta.
const STATUS_FILTERS_OPS = [
  { id: 'all', label: 'Todos' },
  { id: 'asignado', label: 'Asignados' },
  { id: 'pre_resuelto', label: 'Pre-resueltos' },
  { id: 'resuelto', label: 'Resueltos' },
  { id: 'open', label: 'Sin asignar' },
]
const STATUS_FILTERS_CONS = [
  { id: 'all', label: 'Todos' },
  { id: 'open', label: 'Abiertos' },
  { id: 'in_progress', label: 'En curso' },
  { id: 'resolved', label: 'Resueltos' },
  { id: 'escalated', label: 'Escalados' },
]

const AREA_FILTERS = [
  { id: 'all', label: 'Todas las áreas' },
  { id: 'mantenimiento', label: 'Mantenimiento' },
  { id: 'recepcion', label: 'Recepción' },
  { id: 'housekeeping', label: 'Housekeeping' },
  { id: 'general', label: 'General' },
]

// A qué flujo pertenece una categoría (fallback: lo desconocido cae en Operaciones para
// que ningún ticket desaparezca de ambos toggles).
function workflowOf(category) {
  const cons = WORKFLOWS.find((w) => w.id === 'consultas')
  return cons.cats.includes(category) ? 'consultas' : 'operaciones'
}

// Quién figura en el ticket: el nombre si lo hay; "Tarea interna" si lo creó el equipo;
// si no, es un contacto de cara al público sin reserva → "Visitante".
function guestLabel(r) {
  if (r.guest_name) return r.guest_name
  return r.origin === 'staff' ? 'Tarea interna' : 'Visitante'
}

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
const AREA_OPTIONS = ['mantenimiento', 'recepcion', 'housekeeping', 'general']

const PRIORITY_OPTIONS = [
  { id: 'low', label: 'Baja', tone: 'gray' },
  { id: 'medium', label: 'Media', tone: 'blue' },
  { id: 'high', label: 'Alta', tone: 'red' },
]
const PRIORITY_LABELS = { low: 'Baja', medium: 'Media', high: 'Alta' }

function AreaBadge({ area }) {
  if (!area) return <span className="text-xs text-slatey">—</span>
  return <Badge tone="gray">{AREA_LABELS[area] || area}</Badge>
}

function PriorityBadge({ priority }) {
  const p = PRIORITY_OPTIONS.find((x) => x.id === priority)
  if (!p) return null
  return <Badge tone={p.tone}>{p.label}</Badge>
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

// --- Gestión: distinguir lo que hizo el AGENTE solo de lo que tuvo intervención HUMANA ---
// "human" = alguien usó los botones del backoffice (acción manual). El resto (agente/staff/
// huésped) es parte del flujo autónomo que orquesta Aura.
function hadHumanAction(events) {
  return (events || []).some((e) => e.actor_type === 'human')
}

function GestionBadge({ events }) {
  if (hadHumanAction(events)) {
    return <Badge tone="amber"><Hand size={11} className="mr-1" /> Manual</Badge>
  }
  return <Badge tone="green"><Bot size={11} className="mr-1" /> Agente</Badge>
}

// Etiquetas y estilo de cada actor en el timeline.
const ACTOR_META = {
  agent: { label: 'Aura', icon: Bot, cls: 'text-forest-700 bg-forest-50' },
  staff: { label: 'Equipo', icon: User, cls: 'text-hilton-700 bg-hilton-50' },
  guest: { label: 'Huésped', icon: User, cls: 'text-slatey bg-mist' },
  human: { label: 'Backoffice', icon: Hand, cls: 'text-amber-700 bg-amber-50' },
}
const ACTION_LABELS = {
  created: 'creó el ticket', assigned: 'asignó', pre_resolved: 'marcó pre-resuelto',
  resolved: 'resolvió', reopened: 'reabrió', validated: 'validó', priority: 'cambió la prioridad',
}

function TicketTimeline({ events }) {
  if (!events || events.length === 0) {
    return <p className="px-4 py-3 text-xs text-slatey">Sin actividad registrada todavía.</p>
  }
  return (
    <ol className="space-y-2 px-4 py-3">
      {events.map((e) => {
        const meta = ACTOR_META[e.actor_type] || ACTOR_META.agent
        const Icon = meta.icon
        return (
          <li key={e.id} className="flex items-start gap-2.5 text-sm">
            <span className={`mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${meta.cls}`}>
              <Icon size={13} />
            </span>
            <div className="min-w-0">
              <p className="text-ink">
                <span className="font-medium">{e.actor_name || meta.label}</span>{' '}
                <span className="text-slatey">{ACTION_LABELS[e.action] || e.action}</span>
                {e.note && <span className="text-slatey"> · {e.note}</span>}
              </p>
              <p className="text-[11px] tabular-nums text-slatey">{formatDate(e.created_at)}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

// Chip de filtro unificado: mismo lenguaje visual para Estado y Área (una sola familia de
// acento). Antes convivían pills azules (estado) y verdes (área) en filas separadas, lo que
// se veía recargado e inconsistente.
function FilterChip({ active, onClick, label, count }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition ${
        active
          ? 'bg-hilton-600 text-white shadow-card'
          : 'bg-white text-slatey ring-1 ring-mist hover:bg-mist'
      }`}
    >
      {label}
      {count != null && <span className="tabular-nums opacity-70">({count})</span>}
    </button>
  )
}

// Etiqueta corta para nombrar cada grupo de chips (Estado / Área) sin recurrir a otro color.
function FilterGroupLabel({ children }) {
  return <span className="text-[11px] font-medium uppercase tracking-wide text-slatey">{children}</span>
}

export default function TicketsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [workflow, setWorkflow] = useState('operaciones')  // operaciones | consultas
  const [filter, setFilter] = useState('all')              // estado
  const [areaFilter, setAreaFilter] = useState('all')      // área (solo operaciones)
  const [detail, setDetail] = useState(null)               // ticket abierto en el panel

  const load = () => {
    setLoading(true)
    listTickets()
      .then((d) => {
        const list = Array.isArray(d) ? d : []
        setRows(list)
        // Mantener sincronizado el ticket del panel si está abierto.
        setDetail((prev) => (prev ? list.find((t) => t.id === prev.id) || prev : null))
      })
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Al cambiar de flujo, resetear los filtros (los estados no son los mismos).
  const switchWorkflow = (w) => { setWorkflow(w); setFilter('all'); setAreaFilter('all') }

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
  // `fn(id)` devuelve el ticket actualizado (con su bitácora). Mergeamos en la lista y,
  // si el panel está abierto sobre ese ticket, lo refrescamos también.
  const runAction = async (r, fn, okMsg) => {
    setBusyId(r.id)
    try {
      const updated = await fn(r.id)
      setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, ...updated } : x)))
      setDetail((prev) => (prev && prev.id === r.id ? { ...prev, ...updated } : prev))
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

  // Acción rápida según el estado, + botón "Gestionar" que abre el panel con todos los
  // controles (reasignar, nota propia, prioridad). Solo para tickets del flujo operativo.
  const OpsActions = ({ r }) => {
    if (!OPERATIONAL.has(r.status)) return null
    const busy = busyId === r.id
    const Btn = ({ onClick, icon: Icon, label, tone = 'forest' }) => (
      <button onClick={onClick} disabled={busy} title={label}
        className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-medium transition disabled:opacity-50 ${
          tone === 'slate' ? 'border-hilton-200 text-slatey hover:bg-hilton-50'
          : 'border-forest-200 text-forest-700 hover:bg-forest-50'}`}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />} {label}
      </button>
    )
    return (
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {r.status === 'pre_resuelto' && (
          <Btn onClick={() => runAction(r, resolveTicketAdmin, `${r.ticket_number} resuelto`)} icon={CheckCircle2} label="Resolver" />
        )}
        {r.status === 'resuelto' && (
          <Btn onClick={() => runAction(r, reopenTicket, `${r.ticket_number} reabierto`)} icon={RotateCcw} label="Reabrir" tone="slate" />
        )}
        <Btn onClick={() => setDetail(r)} icon={SlidersHorizontal} label="Gestionar" tone="slate" />
      </div>
    )
  }

  // Columnas comunes a los dos flujos.
  const colTicket = { key: 'ticket_number', label: 'Ticket', render: (r) => <span className="font-semibold text-hilton-700">{r.ticket_number}</span> }
  const colGuest = { key: 'guest_name', label: 'Huésped / origen', render: (r) => (
    <div>
      <p className="font-medium text-ink">{guestLabel(r)}</p>
      <p className="text-xs text-slatey">{r.booking_code || (r.room_number ? `Hab. ${r.room_number}` : '')}</p>
    </div>
  ) }
  const colSubject = { key: 'subject', label: 'Asunto', render: (r) => <span className="text-sm">{r.subject}</span> }
  const colStatus = { key: 'status', label: 'Estado', render: (r) => <StatusBadge status={r.status} /> }
  const colDate = { key: 'created_at', label: 'Fecha', sortable: true, render: (r) => formatDate(r.created_at) }
  const colActions = { key: 'actions', label: '', render: (r) => (
    <div className="flex items-center justify-end gap-1.5">
      <OpsActions r={r} />
      <button onClick={() => setDetail(r)} title="Ver detalle"
        className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-hilton-50 hover:text-hilton-700">
        <ChevronRight size={15} />
      </button>
      <DeleteButton r={r} />
    </div>
  ) }

  // Columnas específicas de OPERACIONES (área/asignado/gestión).
  const opsColumns = [
    colTicket, colGuest, colSubject,
    { key: 'area', label: 'Área', render: (r) => <AreaBadge area={r.assigned_area} /> },
    { key: 'assigned', label: 'Asignado a', render: (r) => (
      r.assigned_staff_name
        ? <span className="text-sm text-ink">{r.assigned_staff_name}</span>
        : <span className="text-xs text-slatey">— sin asignar</span>
    ) },
    colStatus,
    { key: 'gestion', label: 'Gestión', render: (r) => (
      <button onClick={() => setDetail(r)} title="Ver actividad del ticket" className="transition hover:opacity-80">
        <GestionBadge events={r.events} />
      </button>
    ) },
    colDate, colActions,
  ]

  // Columnas específicas de CONSULTAS (resolución auto-IA / escalado clásico).
  const consColumns = [
    colTicket, colGuest, colSubject,
    { key: 'category', label: 'Categoría', render: (r) => <CategoryBadge category={r.category} /> },
    colStatus,
    { key: 'resolution', label: 'Resolución', render: (r) => (
      r.escalated
        ? <span className="inline-flex items-center gap-1 text-xs text-red-600">A asesor</span>
        : <span className="inline-flex items-center gap-1 text-xs text-green-600"><Bot size={13} /> Auto (IA)</span>
    ) },
    colDate, colActions,
  ]

  const columns = workflow === 'operaciones' ? opsColumns : consColumns

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-hilton-700">{r.ticket_number}</span>
        <StatusBadge status={r.status} />
      </div>
      <p className="font-medium text-ink">
        {guestLabel(r)}
        {(r.booking_code || r.room_number) && (
          <span className="text-xs font-normal text-slatey"> · {r.booking_code || `Hab. ${r.room_number}`}</span>
        )}
      </p>
      <p className="mt-1 text-sm text-slatey">{r.subject}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <AreaBadge area={r.assigned_area} />
        <OriginBadge origin={r.origin} />
        <button onClick={() => setDetail(r)}><GestionBadge events={r.events} /></button>
        {r.assigned_staff_name && <span className="text-xs text-slatey">→ {r.assigned_staff_name}</span>}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <OpsActions r={r} />
        <div className="flex items-center gap-1">
          <button onClick={() => setDetail(r)} title="Ver actividad"
            className="rounded-lg p-1.5 text-slatey hover:bg-hilton-50 hover:text-hilton-700"><ChevronRight size={15} /></button>
          <DeleteButton r={r} />
        </div>
      </div>
    </div>
  )

  // Pipeline: flujo (toggle) → estado → área → búsqueda/orden/paginación.
  const inWorkflow = rows.filter((r) => workflowOf(r.category) === workflow)
  const byStatus = filter === 'all' ? inWorkflow : inWorkflow.filter((r) => r.status === filter)
  const byArea = (workflow === 'operaciones' && areaFilter !== 'all')
    ? byStatus.filter((r) => (r.assigned_area || 'general') === areaFilter)
    : byStatus
  // Counts de estado sobre el set del flujo actual.
  const counts = inWorkflow.reduce((acc, r) => { acc.all += 1; acc[r.status] = (acc[r.status] || 0) + 1; return acc }, { all: 0 })
  const areaCounts = inWorkflow.reduce((acc, r) => { acc.all += 1; const a = r.assigned_area || 'general'; acc[a] = (acc[a] || 0) + 1; return acc }, { all: 0 })
  const statusFilters = workflow === 'operaciones' ? STATUS_FILTERS_OPS : STATUS_FILTERS_CONS
  const wfCounts = WORKFLOWS.reduce((acc, w) => { acc[w.id] = rows.filter((r) => workflowOf(r.category) === w.id).length; return acc }, {})

  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } =
    useTableControls(byArea, {
      searchKeys: ['ticket_number', 'guest_name', 'subject', 'booking_code'],
      pageSize: 50,
      sortAccessors: { created_at: (r) => r.created_at || '' },
    })

  return (
    <div>
      <PageHeader
        title="Operaciones"
        subtitle="Pedidos y consultas que gestiona Aura. Los pedidos de servicio se asignan al equipo por área y se cierran con validación del huésped."
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
          {/* Toggle de flujo: Operaciones (servicio al equipo) vs Consultas (post-venta). */}
          <div className="mb-4 inline-flex rounded-xl bg-mist p-1">
            {WORKFLOWS.map((w) => (
              <button
                key={w.id}
                onClick={() => switchWorkflow(w.id)}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  workflow === w.id ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey hover:text-ink'
                }`}
              >
                {w.label} <span className="tabular-nums opacity-70">({wfCounts[w.id] ?? 0})</span>
              </button>
            ))}
          </div>

          {/* Banda de filtros: Estado · Área en una sola fila con chips homogéneos, y el
              buscador alineado a la derecha. En mobile todo hace wrap. */}
          <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
            {/* Estado */}
            <FilterGroupLabel>Estado</FilterGroupLabel>
            {statusFilters.map((f) => (
              <FilterChip
                key={f.id}
                active={filter === f.id}
                onClick={() => setFilter(f.id)}
                label={f.label}
                count={counts[f.id] ?? 0}
              />
            ))}

            {/* Área (solo en Operaciones), tras un divisor sutil. */}
            {workflow === 'operaciones' && (
              <>
                <span className="mx-1 hidden h-5 w-px bg-mist sm:block" />
                <FilterGroupLabel>Área</FilterGroupLabel>
                {AREA_FILTERS.map((f) => (
                  <FilterChip
                    key={f.id}
                    active={areaFilter === f.id}
                    onClick={() => setAreaFilter(f.id)}
                    label={f.label}
                    count={areaCounts[f.id] ?? 0}
                  />
                ))}
              </>
            )}

            {/* Buscador: empujado a la derecha en desktop; ancho completo en mobile. */}
            <div className="w-full sm:ml-auto sm:w-72">
              <SearchInput value={query} onChange={setQuery} placeholder="Buscar por ticket, huésped o asunto…" />
            </div>
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

      {detail && (
        <ActivityDrawer
          ticket={detail}
          onClose={() => setDetail(null)}
          onAction={(fn, okMsg) => runAction(detail, fn, okMsg)}
          busy={busyId === detail.id}
        />
      )}
    </div>
  )
}

// Panel lateral: GESTIONAR + VER ACTIVIDAD. Arriba los controles manuales (reasignar,
// prioridad, nota + resolver/reabrir); abajo la bitácora que cuenta la historia del caso.
// Solo los tickets del flujo OPERATIVO se gestionan; las consultas solo muestran actividad.
function ActivityDrawer({ ticket, onClose, onAction, busy }) {
  const isOps = workflowOf(ticket.category) === 'operaciones'
  const [staff, setStaff] = useState([])
  const [area, setArea] = useState(ticket.assigned_area || 'general')
  const [staffId, setStaffId] = useState(ticket.assigned_staff_id || '')
  const [note, setNote] = useState('')

  // Cargar el equipo una vez al abrir (para los selects de reasignación).
  useEffect(() => {
    listStaff().then((d) => setStaff(Array.isArray(d) ? d : [])).catch(() => setStaff([]))
  }, [])

  // Al cambiar el ticket (refresh tras una acción), re-sincronizar área/persona.
  useEffect(() => {
    setArea(ticket.assigned_area || 'general')
    setStaffId(ticket.assigned_staff_id || '')
  }, [ticket.assigned_area, ticket.assigned_staff_id])

  const peopleInArea = staff.filter((m) => m.role === 'staff' && m.active && m.area === area)

  const doAssign = () => onAction(
    (id) => assignTicket(id, { area, staff_id: staffId ? Number(staffId) : undefined }),
    `${ticket.ticket_number} reasignado`,
  )
  const doPreResolve = () => onAction(
    (id) => preResolveTicket(id, note.trim() || 'Resuelto por el equipo'),
    `${ticket.ticket_number} pre-resuelto`,
  )
  const doResolve = () => onAction(resolveTicketAdmin, `${ticket.ticket_number} resuelto`)
  const doReopen = () => onAction(reopenTicket, `${ticket.ticket_number} reabierto`)
  const doPriority = (p) => onAction((id) => setTicketPriority(id, p), `Prioridad actualizada`)

  const Field = ({ label, children }) => (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slatey">{label}</span>
      {children}
    </label>
  )
  const selectCls = 'w-full rounded-lg border border-hilton-200 px-3 py-2 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100'

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-card-lg animate-slide-up">
        <div className="flex items-start justify-between border-b border-mist px-5 py-4">
          <div>
            <p className="font-serif text-lg font-700 text-hilton-700">{ticket.ticket_number}</p>
            <p className="mt-0.5 text-sm text-slatey">{ticket.subject}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={ticket.status} />
              {isOps && <AreaBadge area={ticket.assigned_area} />}
              <PriorityBadge priority={ticket.priority} />
              <GestionBadge events={ticket.events} />
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <ChevronRight size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isOps && (
            <div className="border-b border-mist px-5 py-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slatey">Gestión manual</p>

              {/* Reasignar área + persona */}
              <div className="grid grid-cols-2 gap-2">
                <Field label="Área">
                  <select value={area} onChange={(e) => { setArea(e.target.value); setStaffId('') }} className={selectCls}>
                    {AREA_OPTIONS.map((a) => <option key={a} value={a}>{AREA_LABELS[a]}</option>)}
                  </select>
                </Field>
                <Field label="Asignar a">
                  <select value={staffId} onChange={(e) => setStaffId(e.target.value)} className={selectCls}>
                    <option value="">— sin asignar —</option>
                    {peopleInArea.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </Field>
              </div>
              {peopleInArea.length === 0 && (
                <p className="mt-1 text-[11px] text-amber-600">No hay personal activo en esta área. Cargalo en Equipo.</p>
              )}
              <button onClick={doAssign} disabled={busy}
                className="mt-2 inline-flex items-center gap-1 rounded-lg border border-hilton-200 px-3 py-1.5 text-xs font-medium text-hilton-700 transition hover:bg-hilton-50 disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <User size={13} />} Guardar asignación
              </button>

              {/* Prioridad */}
              <div className="mt-4">
                <span className="mb-1 block text-xs font-medium text-slatey">Prioridad</span>
                <div className="flex gap-1.5">
                  {PRIORITY_OPTIONS.map((p) => (
                    <button key={p.id} onClick={() => doPriority(p.id)} disabled={busy}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
                        ticket.priority === p.id ? 'border-hilton-500 bg-hilton-50 text-hilton-700' : 'border-mist text-slatey hover:bg-mist'
                      }`}>
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Nota + transición de estado */}
              <div className="mt-4">
                <span className="mb-1 block text-xs font-medium text-slatey">Nota de resolución (opcional)</span>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                  placeholder="Ej.: Reparé el aire, quedó enfriando bien."
                  className="w-full resize-none rounded-lg border border-hilton-200 px-3 py-2 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100" />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(ticket.status === 'asignado' || ticket.status === 'open' || ticket.status === 'in_progress') && (
                    <button onClick={doPreResolve} disabled={busy}
                      className="inline-flex items-center gap-1 rounded-lg border border-amber-200 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-50 disabled:opacity-50">
                      <Check size={13} /> Marcar pre-resuelto
                    </button>
                  )}
                  {ticket.status === 'pre_resuelto' && (
                    <button onClick={doResolve} disabled={busy}
                      className="inline-flex items-center gap-1 rounded-lg border border-forest-200 px-3 py-1.5 text-xs font-medium text-forest-700 transition hover:bg-forest-50 disabled:opacity-50">
                      <CheckCircle2 size={13} /> Resolver (cerrar)
                    </button>
                  )}
                  {ticket.status === 'resuelto' && (
                    <button onClick={doReopen} disabled={busy}
                      className="inline-flex items-center gap-1 rounded-lg border border-hilton-200 px-3 py-1.5 text-xs font-medium text-slatey transition hover:bg-hilton-50 disabled:opacity-50">
                      <RotateCcw size={13} /> Reabrir
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          <p className="px-4 pt-4 text-xs font-semibold uppercase tracking-wide text-slatey">Actividad</p>
          <TicketTimeline events={ticket.events} />

          {/* La charla con Aura que originó el ticket (vía session_id). */}
          <p className="border-t border-mist px-4 pt-4 text-xs font-semibold uppercase tracking-wide text-slatey">Conversación</p>
          <ChatTranscript sessionId={ticket.session_id} />
        </div>

        {ticket.resolution_note && (
          <div className="border-t border-mist bg-mist/40 px-5 py-3">
            <p className="text-xs font-semibold text-slatey">Última nota de resolución</p>
            <p className="mt-0.5 text-sm text-ink">{ticket.resolution_note}</p>
          </div>
        )}
      </aside>
    </div>
  )
}
