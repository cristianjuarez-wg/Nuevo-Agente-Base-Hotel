import { useState, useEffect } from 'react'
import { Tag, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, X, Save, Loader2 } from 'lucide-react'
import { listPromotions, savePromotion, patchPromotionStatus, deletePromotion } from '../../../services/api'
import { PageHeader, Badge, Loading, EmptyState, formatDate } from '../../ui'

const DISCOUNT_TYPES = [
  { value: 'percentage', label: 'Porcentaje (%)' },
  { value: 'free_night', label: 'Noches bonificadas' },
  { value: 'other', label: 'Otro / Descripción libre' },
]

function vigenciaLabel(promo) {
  const now = new Date()
  if (promo.status !== 'active') return null
  if (promo.valid_until) {
    const until = new Date(promo.valid_until)
    if (until < now) return 'vencida'
  }
  if (promo.valid_from) {
    const from = new Date(promo.valid_from)
    if (from > now) return 'próxima'
  }
  return 'vigente'
}

function VigenciaBadge({ promo }) {
  const estado = vigenciaLabel(promo)
  if (!estado) return <Badge tone="gray">inactiva</Badge>
  if (estado === 'vigente') return <Badge tone="green">vigente</Badge>
  if (estado === 'próxima') return <Badge tone="blue">próxima</Badge>
  if (estado === 'vencida') return <Badge tone="red">vencida</Badge>
  return null
}

function formatDateInput(iso) {
  if (!iso) return ''
  return iso.slice(0, 10)
}

export default function PromotionsView() {
  const [promos, setPromos] = useState([])
  const [loading, setLoading] = useState(true)
  const [editPromo, setEditPromo] = useState(null)   // null = cerrado, {} = nuevo, {...} = editar
  const [confirmDelete, setConfirmDelete] = useState(null)

  const load = () => {
    setLoading(true)
    listPromotions()
      .then((p) => setPromos(p || []))
      .catch(() => setPromos([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const toggleStatus = async (promo) => {
    const next = promo.status === 'active' ? 'inactive' : 'active'
    await patchPromotionStatus(promo.id, next)
    load()
  }

  const handleDelete = async (promo) => {
    await deletePromotion(promo.id)
    setConfirmDelete(null)
    load()
  }

  if (loading) return <Loading label="Cargando promociones…" />

  return (
    <div>
      <PageHeader
        title="Promociones"
        subtitle="Gestioná las ofertas y descuentos que el agente Aura comunica a los huéspedes."
        right={
          <button
            onClick={() => setEditPromo({})}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700"
          >
            <Plus size={16} /> Nueva promoción
          </button>
        }
      />

      {promos.length === 0 ? (
        <EmptyState
          icon={Tag}
          title="Aún no hay promociones"
          desc="Cargá la primera oferta y el agente la comunicará automáticamente a los huéspedes."
        />
      ) : (
        <div className="space-y-3">
          {promos.map((p) => (
            <div
              key={p.id}
              className="flex flex-col gap-3 rounded-2xl border border-hilton-100 bg-white p-4 shadow-card sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="font-semibold text-ink">{p.name}</span>
                  <VigenciaBadge promo={p} />
                  {p.discount_type === 'percentage' && p.discount_value != null && (
                    <Badge tone="amber">{p.discount_value}% off</Badge>
                  )}
                  {p.discount_type === 'free_night' && p.discount_value != null && (
                    <Badge tone="hilton">{p.discount_value} noche(s) gratis</Badge>
                  )}
                </div>
                <p className="text-sm text-slatey line-clamp-2">{p.description}</p>
                {p.conditions && (
                  <p className="mt-1 text-xs text-slatey/70">Cond.: {p.conditions}</p>
                )}
                {(p.valid_from || p.valid_until) && (
                  <p className="mt-1 text-xs text-slatey/60">
                    {p.valid_from ? `Desde ${formatDate(p.valid_from)}` : ''}
                    {p.valid_from && p.valid_until ? ' — ' : ''}
                    {p.valid_until ? `Hasta ${formatDate(p.valid_until)}` : ''}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => toggleStatus(p)}
                  title={p.status === 'active' ? 'Desactivar' : 'Activar'}
                  className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink"
                >
                  {p.status === 'active'
                    ? <ToggleRight size={20} className="text-forest-500" />
                    : <ToggleLeft size={20} />}
                </button>
                <button
                  onClick={() => setEditPromo(p)}
                  title="Editar"
                  className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink"
                >
                  <Pencil size={16} />
                </button>
                <button
                  onClick={() => setConfirmDelete(p)}
                  title="Eliminar"
                  className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editPromo !== null && (
        <PromoModal
          promo={editPromo}
          onClose={() => setEditPromo(null)}
          onSaved={() => { setEditPromo(null); load() }}
        />
      )}

      {confirmDelete && (
        <ConfirmModal
          title={`¿Eliminar "${confirmDelete.name}"?`}
          message="Esta acción no se puede deshacer. La promoción se quitará también del conocimiento del agente."
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => handleDelete(confirmDelete)}
        />
      )}
    </div>
  )
}

// ── Modal de formulario ────────────────────────────────────────────────────

function PromoModal({ promo, onClose, onSaved }) {
  const isNew = !promo.id
  const [name, setName] = useState(promo.name || '')
  const [description, setDescription] = useState(promo.description || '')
  const [conditions, setConditions] = useState(promo.conditions || '')
  const [discountType, setDiscountType] = useState(promo.discount_type || 'other')
  const [discountValue, setDiscountValue] = useState(promo.discount_value ?? '')
  const [validFrom, setValidFrom] = useState(formatDateInput(promo.valid_from))
  const [validUntil, setValidUntil] = useState(formatDateInput(promo.valid_until))
  const [status, setStatus] = useState(promo.status || 'active')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    if (!name.trim() || !description.trim()) {
      setError('El nombre y la descripción son obligatorios.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await savePromotion(
        {
          name: name.trim(),
          description: description.trim(),
          conditions: conditions.trim() || null,
          discount_type: discountType,
          discount_value: discountValue !== '' ? parseFloat(discountValue) : null,
          valid_from: validFrom || null,
          valid_until: validUntil || null,
          status,
        },
        promo.id,
      )
      onSaved()
    } catch {
      setError('No se pudo guardar la promoción. Intentá de nuevo.')
      setSaving(false)
    }
  }

  return (
    <Modal title={isNew ? 'Nueva promoción' : 'Editar promoción'} icon={Tag} onClose={onClose}>
      <div className="space-y-4">
        <Field label="Nombre *" value={name} onChange={setName} placeholder="Ej: Promo 4x3" />

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Descripción *</span>
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)}
            rows={3} placeholder="Descripción completa que el agente comunicará al huésped…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Condiciones</span>
          <textarea
            value={conditions} onChange={(e) => setConditions(e.target.value)}
            rows={2} placeholder="Restricciones, requisitos, mínimo de noches…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Tipo de descuento</span>
            <select
              value={discountType} onChange={(e) => setDiscountType(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            >
              {DISCOUNT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>

          {discountType !== 'other' && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-ink">
                {discountType === 'percentage' ? 'Porcentaje (%)' : 'Noches bonificadas'}
              </span>
              <input
                type="number" min="0" step={discountType === 'percentage' ? '1' : '1'}
                value={discountValue} onChange={(e) => setDiscountValue(e.target.value)}
                placeholder={discountType === 'percentage' ? '20' : '1'}
                className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
              />
            </label>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Válida desde</span>
            <input
              type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Válida hasta</span>
            <input
              type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)}
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </label>
        </div>

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

// ── Modal de confirmación de borrado ──────────────────────────────────────

function ConfirmModal({ title, message, onCancel, onConfirm }) {
  const [deleting, setDeleting] = useState(false)
  const confirm = async () => {
    setDeleting(true)
    await onConfirm()
  }
  return (
    <Modal title={title} icon={Trash2} onClose={onCancel}>
      <p className="mb-6 text-sm text-slatey">{message}</p>
      <div className="flex justify-end gap-3">
        <button onClick={onCancel} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">
          Cancelar
        </button>
        <button
          onClick={confirm} disabled={deleting}
          className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-60"
        >
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
          Eliminar
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
            {Icon && (
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
                <Icon size={18} />
              </div>
            )}
            <h3 className="font-serif text-lg font-700 text-ink">{title}</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
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
