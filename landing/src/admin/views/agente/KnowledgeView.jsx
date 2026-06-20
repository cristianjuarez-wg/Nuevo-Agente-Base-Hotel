import { useEffect, useState } from 'react'
import {
  CreditCard, Clock, XCircle, Dog, BellRing, HelpCircle, FileText,
  MapPin, Plus, Pencil, Trash2, X, Save, ExternalLink, Loader2,
} from 'lucide-react'
import {
  listKnowledgeEntries, saveKnowledgeEntry, deleteKnowledgeEntry,
  listPlaces, savePlace, deletePlace, MEDIA_BASE,
} from '../../../services/api'
import { PageHeader, Loading, Badge } from '../../ui'
import ImageInput from '../../components/ImageInput'

// Categorías estructuradas (formularios). Orden = orden de aparición.
const CATEGORIES = [
  { id: 'pagos', label: 'Pagos y transferencia', icon: CreditCard, hint: 'CBU, alias, medios de pago' },
  { id: 'checkin', label: 'Check-in / Check-out', icon: Clock, hint: 'Horarios y políticas de ingreso' },
  { id: 'cancelacion', label: 'Cancelación / no-show', icon: XCircle, hint: 'Condiciones de cancelación' },
  { id: 'mascotas', label: 'Mascotas y convivencia', icon: Dog, hint: 'Mascotas, niños, fumadores' },
  { id: 'servicios', label: 'Servicios e instalaciones', icon: BellRing, hint: 'Desayuno, wifi, cochera…' },
  { id: 'faq', label: 'Preguntas frecuentes', icon: HelpCircle, hint: 'Preguntas y respuestas' },
  { id: 'general', label: 'Información general', icon: FileText, hint: 'Otra info para el agente' },
]

const PLACE_CATEGORIES = [
  { id: 'excursion', label: 'Excursión' },
  { id: 'gastronomia', label: 'Gastronomía' },
  { id: 'atraccion', label: 'Atracción' },
  { id: 'transporte', label: 'Transporte' },
  { id: 'hotel', label: 'Hotel' },
]

function resolveUrl(url) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${MEDIA_BASE}${url}`
}

export default function KnowledgeView() {
  const [entries, setEntries] = useState([])
  const [places, setPlaces] = useState([])
  const [loading, setLoading] = useState(true)
  const [editCategory, setEditCategory] = useState(null)  // category id en edición
  const [editPlace, setEditPlace] = useState(null)        // place obj o {} (nuevo) o null

  const load = () => {
    setLoading(true)
    Promise.all([listKnowledgeEntries().catch(() => []), listPlaces().catch(() => [])])
      .then(([e, p]) => { setEntries(e || []); setPlaces(p || []) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const entriesByCategory = (catId) => entries.filter((e) => e.category === catId)

  if (loading) return <Loading label="Cargando base de conocimiento…" />

  return (
    <div>
      <PageHeader
        title="Base de conocimiento del agente"
        subtitle="El agente Aura usa esta información para responder. Cada cambio se aplica al instante, sin actualizar el sitio."
      />

      {/* Información del hotel — categorías */}
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slatey">Información del hotel</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon
          const count = entriesByCategory(cat.id).length
          return (
            <button
              key={cat.id}
              onClick={() => setEditCategory(cat.id)}
              className="flex items-start gap-3 rounded-2xl bg-white p-5 text-left shadow-card transition hover:shadow-card-lg"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-hilton-50 text-hilton-600">
                <Icon size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">{cat.label}</p>
                <p className="truncate text-xs text-slatey">{cat.hint}</p>
                <div className="mt-2">
                  {count > 0 ? (
                    <Badge tone="green">{count === 1 ? 'Cargado' : `${count} cargados`}</Badge>
                  ) : (
                    <Badge tone="gray">Sin cargar</Badge>
                  )}
                </div>
              </div>
              <Pencil size={15} className="mt-1 shrink-0 text-slatey" />
            </button>
          )
        })}
      </div>

      {/* Lugares y excursiones */}
      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slatey">Lugares y excursiones</h2>
        <button
          onClick={() => setEditPlace({})}
          className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-600 px-3 py-1.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700"
        >
          <Plus size={15} /> Agregar lugar
        </button>
      </div>
      <div className="mt-3 space-y-2">
        {places.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-hilton-200 bg-white py-10 text-center text-sm text-slatey">
            Todavía no cargaste lugares ni excursiones.
          </div>
        ) : (
          places.map((p) => (
            <div key={p.id} className="flex items-center gap-3 rounded-2xl bg-white p-3 shadow-card">
              <div className="h-12 w-16 shrink-0 overflow-hidden rounded-lg bg-mist">
                {p.image_url ? (
                  <img src={resolveUrl(p.image_url)} alt={p.name} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-slatey">
                    <MapPin size={16} />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">{p.name}</p>
                <p className="truncate text-xs capitalize text-slatey">
                  {PLACE_CATEGORIES.find((c) => c.id === p.category)?.label || p.category}
                  {p.price_info ? ` · ${p.price_info}` : ''}
                </p>
              </div>
              {p.maps_url && (
                <a
                  href={p.maps_url} target="_blank" rel="noreferrer"
                  className="hidden items-center gap-1 text-xs text-hilton-600 hover:underline sm:inline-flex"
                >
                  <MapPin size={13} /> Maps
                </a>
              )}
              <button onClick={() => setEditPlace(p)} aria-label="Editar" className="rounded-lg p-2 text-slatey hover:bg-mist">
                <Pencil size={15} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Modales */}
      {editCategory && (
        <CategoryModal
          category={CATEGORIES.find((c) => c.id === editCategory)}
          entries={entriesByCategory(editCategory)}
          onClose={() => setEditCategory(null)}
          onSaved={() => { setEditCategory(null); load() }}
        />
      )}
      {editPlace && (
        <PlaceModal
          place={editPlace}
          onClose={() => setEditPlace(null)}
          onSaved={() => { setEditPlace(null); load() }}
        />
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Modal de categoría: formulario adaptado según la categoría (pagos, faq, o genérico).
// ───────────────────────────────────────────────────────────────────────────
function CategoryModal({ category, entries, onClose, onSaved }) {
  // Para simplificar: una entrada por categoría (la primera existente, o nueva).
  const existing = entries[0] || null
  const [title, setTitle] = useState(existing?.title || category.label)
  const [content, setContent] = useState(existing?.content || '')
  const [data, setData] = useState(existing?.data || {})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isPagos = category.id === 'pagos'
  const isFaq = category.id === 'faq'

  const setDataField = (k, v) => setData((d) => ({ ...d, [k]: v }))

  const save = async () => {
    setSaving(true); setError('')
    try {
      await saveKnowledgeEntry(
        { category: category.id, title: title.trim() || category.label, content, data, status: 'active' },
        existing?.id,
      )
      onSaved()
    } catch (e) {
      setError('No se pudo guardar. Intentá de nuevo.')
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!existing) return
    setSaving(true)
    try { await deleteKnowledgeEntry(existing.id); onSaved() }
    catch { setError('No se pudo borrar.'); setSaving(false) }
  }

  const Icon = category.icon

  return (
    <Modal onClose={onClose} title={category.label} icon={Icon}>
      {isPagos ? (
        <PagosForm data={data} setDataField={setDataField} content={content} setContent={setContent} />
      ) : isFaq ? (
        <FaqForm data={data} setData={setData} />
      ) : (
        <GenericForm
          title={title} setTitle={setTitle}
          content={content} setContent={setContent}
          label={category.label}
        />
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-6 flex items-center justify-between">
        <div>
          {existing && (
            <button
              onClick={remove} disabled={saving}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 disabled:opacity-60"
            >
              <Trash2 size={15} /> Borrar
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="text-sm font-medium text-slatey hover:text-ink">Cancelar</button>
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

function PagosForm({ data, setDataField, content, setContent }) {
  const MEDIOS = ['Efectivo', 'Tarjeta de crédito/débito', 'Transferencia bancaria', 'Mercado Pago']
  const selected = data.medios || []
  const toggleMedio = (m) =>
    setDataField('medios', selected.includes(m) ? selected.filter((x) => x !== m) : [...selected, m])

  return (
    <div className="space-y-4">
      <div>
        <Label>Medios de pago aceptados</Label>
        <div className="flex flex-wrap gap-2">
          {MEDIOS.map((m) => {
            const on = selected.includes(m)
            return (
              <button
                key={m} type="button" onClick={() => toggleMedio(m)}
                className={`rounded-full border px-3 py-1.5 text-sm transition ${
                  on ? 'border-hilton-600 bg-hilton-50 text-hilton-700' : 'border-hilton-200 text-slatey hover:bg-mist'
                }`}
              >
                {on ? '✓ ' : ''}{m}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <Label>Datos para transferencia bancaria</Label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Titular" value={data.titular} onChange={(v) => setDataField('titular', v)} />
          <Field label="Banco" value={data.banco} onChange={(v) => setDataField('banco', v)} />
          <Field label="CBU" value={data.cbu} onChange={(v) => setDataField('cbu', v)} />
          <Field label="Alias" value={data.alias} onChange={(v) => setDataField('alias', v)} />
        </div>
      </div>

      <div>
        <Label>Notas adicionales (opcional)</Label>
        <textarea
          value={content} onChange={(e) => setContent(e.target.value)} rows={2}
          placeholder="Ej: Se requiere una seña del 30% para confirmar la reserva."
          className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
        />
      </div>
    </div>
  )
}

function FaqForm({ data, setData }) {
  const items = data.items || []
  const update = (i, k, v) => {
    const next = items.map((it, idx) => (idx === i ? { ...it, [k]: v } : it))
    setData({ ...data, items: next })
  }
  const add = () => setData({ ...data, items: [...items, { q: '', a: '' }] })
  const remove = (i) => setData({ ...data, items: items.filter((_, idx) => idx !== i) })

  return (
    <div className="space-y-3">
      {items.length === 0 && (
        <p className="text-sm text-slatey">Agregá las preguntas más comunes de tus huéspedes.</p>
      )}
      {items.map((it, i) => (
        <div key={i} className="rounded-xl border border-hilton-100 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slatey">Pregunta {i + 1}</span>
            <button onClick={() => remove(i)} className="text-slatey hover:text-red-600"><X size={15} /></button>
          </div>
          <input
            value={it.q} onChange={(e) => update(i, 'q', e.target.value)}
            placeholder="Pregunta…"
            className="mb-2 w-full rounded-lg border border-hilton-200 px-3 py-2 text-sm focus:border-hilton-500 focus:outline-none"
          />
          <textarea
            value={it.a} onChange={(e) => update(i, 'a', e.target.value)} rows={2}
            placeholder="Respuesta…"
            className="w-full rounded-lg border border-hilton-200 px-3 py-2 text-sm focus:border-hilton-500 focus:outline-none"
          />
        </div>
      ))}
      <button onClick={add} className="inline-flex items-center gap-1.5 text-sm font-medium text-hilton-600 hover:text-hilton-700">
        <Plus size={15} /> Agregar pregunta
      </button>
    </div>
  )
}

function GenericForm({ title, setTitle, content, setContent, label }) {
  return (
    <div className="space-y-4">
      <Field label="Título" value={title} onChange={setTitle} placeholder={label} />
      <div>
        <Label>Contenido</Label>
        <textarea
          value={content} onChange={(e) => setContent(e.target.value)} rows={6}
          placeholder="Escribí la información que el agente debe conocer…"
          className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
        />
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Modal de lugar / excursión
// ───────────────────────────────────────────────────────────────────────────
function PlaceModal({ place, onClose, onSaved }) {
  const isNew = !place.id
  const [form, setForm] = useState({
    name: place.name || '',
    category: place.category || 'atraccion',
    description: place.description || '',
    image_url: place.image_url || '',
    maps_url: place.maps_url || '',
    address: place.address || '',
    price_info: place.price_info || '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    if (!form.name.trim()) { setError('El nombre es obligatorio.'); return }
    setSaving(true); setError('')
    try { await savePlace(form, place.id); onSaved() }
    catch { setError('No se pudo guardar.'); setSaving(false) }
  }
  const remove = async () => {
    setSaving(true)
    try { await deletePlace(place.id); onSaved() }
    catch { setError('No se pudo borrar.'); setSaving(false) }
  }

  return (
    <Modal onClose={onClose} title={isNew ? 'Nuevo lugar' : 'Editar lugar'} icon={MapPin}>
      <div className="space-y-4">
        <Field label="Nombre" value={form.name} onChange={(v) => set('name', v)} placeholder="Ej: Cerro Catedral" />
        <div>
          <Label>Categoría</Label>
          <select
            value={form.category} onChange={(e) => set('category', e.target.value)}
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
          >
            {PLACE_CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <Label>Descripción</Label>
          <textarea
            value={form.description} onChange={(e) => set('description', e.target.value)} rows={3}
            placeholder="Breve descripción del lugar…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Precio (texto libre)" value={form.price_info} onChange={(v) => set('price_info', v)} placeholder="Desde USD 50" />
          <Field label="Dirección" value={form.address} onChange={(v) => set('address', v)} />
        </div>
        <div>
          <Label>Link de Google Maps</Label>
          <input
            type="url" value={form.maps_url} onChange={(e) => set('maps_url', e.target.value)}
            placeholder="https://maps.google.com/…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
          />
        </div>
        <div>
          <Label>Imagen</Label>
          <ImageInput value={form.image_url} onChange={(v) => set('image_url', v)} />
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-6 flex items-center justify-between">
        <div>
          {!isNew && (
            <button onClick={remove} disabled={saving} className="inline-flex items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 disabled:opacity-60">
              <Trash2 size={15} /> Borrar
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="text-sm font-medium text-slatey hover:text-ink">Cancelar</button>
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

// ───────────────────────────────────────────────────────────────────────────
// Primitivas locales
// ───────────────────────────────────────────────────────────────────────────
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

function Label({ children }) {
  return <p className="mb-1.5 text-sm font-medium text-ink">{children}</p>
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        type="text" value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
    </label>
  )
}
