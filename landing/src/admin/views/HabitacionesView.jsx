import { useState, useEffect } from 'react'
import { Hotel, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, X, Save, Loader2, Users, BedDouble } from 'lucide-react'
import { listRoomsAdmin, saveRoom, patchRoomStatus, deleteRoom } from '../../services/api'
import { PageHeader, Badge, Loading, EmptyState, formatUSD, formatARS } from '../ui'
import ImageInput from '../components/ImageInput'

export default function HabitacionesView() {
  const [rooms, setRooms] = useState([])
  const [rate, setRate] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editRoom, setEditRoom] = useState(null)        // null=cerrado, {}=nueva, {...}=editar
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [actionError, setActionError] = useState('')

  const load = (silent = false) => {
    if (!silent) setLoading(true)
    listRoomsAdmin()
      .then((d) => {
        setRooms(d.rooms || [])
        setRate(d.exchange_rate || null)
      })
      .catch(() => setRooms([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const toggleStatus = async (room) => {
    const next = room.status === 'active' ? 'inactive' : 'active'
    await patchRoomStatus(room.id, next)
    load(true)
  }

  const handleDelete = async (room) => {
    setActionError('')
    try {
      await deleteRoom(room.id)
      setConfirmDelete(null)
      load(true)
    } catch (e) {
      const msg = e?.response?.data?.message || e?.response?.data?.detail || 'No se pudo eliminar.'
      setActionError(msg)
    }
  }

  if (loading) return <Loading label="Cargando habitaciones…" />

  return (
    <div>
      <PageHeader
        title="Habitaciones"
        subtitle={
          rate
            ? `Precios en USD (fuente de verdad). El ARS se calcula con la cotización vigente: ${formatARS(rate.rate)} · ${rate.source}.`
            : 'Gestioná los tipos de habitación, sus precios y disponibilidad.'
        }
        right={
          <button
            onClick={() => setEditRoom({})}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700"
          >
            <Plus size={16} /> Nueva habitación
          </button>
        }
      />

      {rooms.length === 0 ? (
        <EmptyState
          icon={Hotel}
          title="Aún no hay habitaciones"
          desc="Cargá el primer tipo de habitación con su precio en USD."
        />
      ) : (
        <div className="space-y-3">
          {rooms.map((r) => (
            <div
              key={r.id}
              className={`flex flex-col gap-3 rounded-2xl border bg-white p-4 shadow-card sm:flex-row sm:items-center sm:justify-between ${
                r.status === 'inactive' ? 'border-hilton-100 opacity-60' : 'border-hilton-100'
              }`}
            >
              <div className="flex gap-4 flex-1 min-w-0">
                {r.images?.[0] && (
                  <img
                    src={resolveImg(r.images[0])}
                    alt={r.room_type}
                    className="h-16 w-24 shrink-0 rounded-xl border border-hilton-100 object-cover"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="font-semibold text-ink">{r.room_type}</span>
                    <Badge tone={r.status === 'active' ? 'green' : 'gray'}>
                      {r.status === 'active' ? 'activa' : 'inactiva'}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slatey">
                    <span className="inline-flex items-center gap-1"><Users size={13} /> {r.capacity} huésped(es)</span>
                    {r.bed_config && <span className="inline-flex items-center gap-1"><BedDouble size={13} /> {r.bed_config}</span>}
                    <span>{r.total_units} unidad(es)</span>
                  </div>
                  <p className="mt-1.5 text-sm tabular-nums">
                    <span className="font-semibold text-hilton-700">{formatUSD(r.base_price_usd)}</span>
                    <span className="text-slatey"> / noche · {formatARS(r.base_price_ars)}</span>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => toggleStatus(r)}
                  title={r.status === 'active' ? 'Desactivar' : 'Activar'}
                  className={`rounded-lg p-2 transition ${
                    r.status === 'active'
                      ? 'bg-forest-100 text-forest-600 hover:bg-forest-200'
                      : 'text-slatey/50 hover:bg-mist hover:text-slatey'
                  }`}
                >
                  {r.status === 'active' ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                </button>
                <button onClick={() => setEditRoom(r)} title="Editar" className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink">
                  <Pencil size={16} />
                </button>
                <button onClick={() => setConfirmDelete(r)} title="Eliminar" className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editRoom !== null && (
        <RoomModal
          room={editRoom}
          rate={rate}
          onClose={() => setEditRoom(null)}
          onSaved={() => { setEditRoom(null); load(true) }}
        />
      )}

      {confirmDelete && (
        <ConfirmModal
          title={`¿Eliminar "${confirmDelete.room_type}"?`}
          message="Esta acción no se puede deshacer. Si la habitación tiene reservas, desactivala en lugar de eliminarla."
          error={actionError}
          onCancel={() => { setConfirmDelete(null); setActionError('') }}
          onConfirm={() => handleDelete(confirmDelete)}
        />
      )}
    </div>
  )
}

// Resuelve /media o /fotos a URL servible (mismo criterio que el chat).
function resolveImg(url) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return url
}

// ── Modal de formulario ──────────────────────────────────────────────────

function RoomModal({ room, rate, onClose, onSaved }) {
  const isNew = !room.id
  const [roomType, setRoomType] = useState(room.room_type || '')
  const [description, setDescription] = useState(room.description || '')
  const [capacity, setCapacity] = useState(room.capacity ?? 2)
  const [basePriceUsd, setBasePriceUsd] = useState(room.base_price_usd ?? '')
  const [totalUnits, setTotalUnits] = useState(room.total_units ?? 1)
  const [bedConfig, setBedConfig] = useState(room.bed_config || '')
  const [view, setView] = useState(room.view || '')
  const [image, setImage] = useState(room.images?.[0] || '')
  const [amenitiesText, setAmenitiesText] = useState((room.amenities || []).join(', '))
  const [status, setStatus] = useState(room.status || 'active')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // ARS de referencia en vivo, según la cotización vigente.
  const arsPreview = rate && basePriceUsd !== '' && !isNaN(Number(basePriceUsd))
    ? formatARS(Number(basePriceUsd) * rate.rate)
    : null

  const save = async () => {
    if (!roomType.trim()) { setError('El tipo de habitación es obligatorio.'); return }
    if (basePriceUsd === '' || isNaN(Number(basePriceUsd))) { setError('Ingresá un precio en USD válido.'); return }
    setSaving(true)
    setError('')
    try {
      await saveRoom({
        room_type: roomType.trim(),
        description: description.trim() || null,
        capacity: parseInt(capacity) || 1,
        base_price_usd: Number(basePriceUsd),
        total_units: parseInt(totalUnits) || 0,
        bed_config: bedConfig.trim() || null,
        view: view.trim() || null,
        images: image ? [image] : [],
        amenities: amenitiesText.split(',').map((a) => a.trim()).filter(Boolean),
        status,
      }, room.id)
      onSaved()
    } catch {
      setError('No se pudo guardar. Intentá de nuevo.')
      setSaving(false)
    }
  }

  return (
    <Modal title={isNew ? 'Nueva habitación' : 'Editar habitación'} icon={Hotel} onClose={onClose}>
      <div className="space-y-4">
        <Field label="Tipo de habitación *" value={roomType} onChange={setRoomType} placeholder="Ej: King" />

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Descripción</span>
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)}
            rows={2} placeholder="Descripción de la habitación…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Precio USD / noche *</span>
            <input
              type="number" min="0" step="0.01" inputMode="decimal"
              value={basePriceUsd} onChange={(e) => setBasePriceUsd(e.target.value)}
              placeholder="120"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
            {arsPreview && <span className="mt-1 block text-xs text-slatey">≈ {arsPreview} (cotización vigente)</span>}
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Capacidad (huéspedes)</span>
            <input
              type="number" min="1" value={capacity} onChange={(e) => setCapacity(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Unidades totales</span>
            <input
              type="number" min="0" value={totalUnits} onChange={(e) => setTotalUnits(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Estado</span>
            <select
              value={status} onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            >
              <option value="active">Activa</option>
              <option value="inactive">Inactiva</option>
            </select>
          </label>
        </div>

        <Field label="Configuración de camas" value={bedConfig} onChange={setBedConfig} placeholder="1 cama king" />
        <Field label="Vista" value={view} onChange={setView} placeholder="Lago o ciudad" />

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Amenities (separados por coma)</span>
          <textarea
            value={amenitiesText} onChange={(e) => setAmenitiesText(e.target.value)}
            rows={2} placeholder="WiFi gratis, Minibar, Smart TV"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none"
          />
        </label>

        <div>
          <span className="mb-1 block text-sm font-medium text-ink">Imagen principal</span>
          <ImageInput value={image} onChange={setImage} />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">
            Cancelar
          </button>
          <button
            onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            Guardar
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── Modal de confirmación ──────────────────────────────────────────────────

function ConfirmModal({ title, message, error, onCancel, onConfirm }) {
  const [deleting, setDeleting] = useState(false)
  const confirm = async () => { setDeleting(true); await onConfirm(); setDeleting(false) }
  return (
    <Modal title={title} icon={Trash2} onClose={onCancel}>
      <p className="mb-4 text-sm text-slatey">{message}</p>
      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="flex justify-end gap-3">
        <button onClick={onCancel} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">Cancelar</button>
        <button onClick={confirm} disabled={deleting} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-60">
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} Eliminar
        </button>
      </div>
    </Modal>
  )
}

// ── Primitivas locales ─────────────────────────────────────────────────────

function Modal({ title, icon: Icon, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            {Icon && <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600"><Icon size={18} /></div>}
            <h3 className="font-serif text-lg font-700 text-ink">{title}</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        type="text" value={value || ''} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
    </label>
  )
}
