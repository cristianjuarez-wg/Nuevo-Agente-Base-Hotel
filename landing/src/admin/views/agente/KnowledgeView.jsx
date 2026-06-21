import { useEffect, useState } from 'react'
import {
  CreditCard, Clock, XCircle, Dog, BellRing, HelpCircle, FileText,
  MapPin, Plus, Pencil, Trash2, X, Save, Loader2, Upload, FileUp,
} from 'lucide-react'
import {
  listKnowledgeEntries, saveKnowledgeEntry, deleteKnowledgeEntry,
  listPlaces, savePlace, deletePlace, MEDIA_BASE,
  listKnowledgeDocuments, uploadKnowledgeDocument, uploadKnowledgeTextDocument,
  setKnowledgeEntryStatus, deleteKnowledgeEntry as deleteDoc,
  extractFromDocument,
} from '../../../services/api'
import { Sparkles, Wand2 } from 'lucide-react'
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
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [editCategory, setEditCategory] = useState(null)  // category id en edición
  const [editPlace, setEditPlace] = useState(null)        // place obj o {} (nuevo) o null
  const [docModal, setDocModal] = useState(false)

  const load = () => {
    setLoading(true)
    Promise.all([
      listKnowledgeEntries().catch(() => []),
      listPlaces().catch(() => []),
      listKnowledgeDocuments().catch(() => []),
    ])
      .then(([e, p, d]) => { setEntries(e || []); setPlaces(p || []); setDocuments(d || []) })
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const removeDocument = async (id) => {
    await deleteDoc(id)
    load()
  }
  const toggleDocument = async (doc) => {
    await setKnowledgeEntryStatus(doc.id, doc.status === 'active' ? 'inactive' : 'active')
    load()
  }

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
                <p className="flex items-center gap-2 truncate font-medium text-ink">
                  <span className="truncate">{p.name}</span>
                  {p.is_partner && <Badge tone="green">Amigo</Badge>}
                </p>
                <p className="truncate text-xs capitalize text-slatey">
                  {PLACE_CATEGORIES.find((c) => c.id === p.category)?.label || p.category}
                  {p.discount ? ` · ${p.discount}` : p.price_info ? ` · ${p.price_info}` : ''}
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

      {/* Documentos libres */}
      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slatey">Documentos</h2>
        <button
          onClick={() => setDocModal(true)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-600 px-3 py-1.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700"
        >
          <FileUp size={15} /> Subir / pegar
        </button>
      </div>
      <p className="mt-1 text-xs text-slatey">
        Subí un PDF o pegá texto. Elegí siempre un tema para que el agente sepa de qué trata.
      </p>
      <div className="mt-3 space-y-2">
        {documents.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-hilton-200 bg-white py-10 text-center text-sm text-slatey">
            Todavía no cargaste documentos.
          </div>
        ) : (
          documents.map((d) => {
            const cat = CATEGORIES.find((c) => c.id === d.category)
            return (
              <div key={d.id} className="flex items-center gap-3 rounded-2xl bg-white p-3 shadow-card">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
                  <FileText size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink">{d.title}</p>
                  <p className="truncate text-xs text-slatey">
                    {cat?.label || d.category} · {{ pdf: 'PDF', markdown: 'Markdown' }[d.data?.doc_kind] || 'Texto'}
                  </p>
                </div>
                <Badge tone={d.status === 'active' ? 'green' : 'gray'}>
                  {d.status === 'active' ? 'Activo' : 'Inactivo'}
                </Badge>
                <button onClick={() => toggleDocument(d)} className="text-xs font-medium text-slatey hover:text-ink">
                  {d.status === 'active' ? 'Desactivar' : 'Activar'}
                </button>
                <button onClick={() => removeDocument(d.id)} aria-label="Borrar" className="rounded-lg p-2 text-slatey hover:bg-mist hover:text-red-600">
                  <Trash2 size={15} />
                </button>
              </div>
            )
          })
        )}
      </div>

      {/* Modales */}
      {docModal && (
        <DocumentModal
          categories={CATEGORIES}
          onClose={() => setDocModal(false)}
          onSaved={() => { setDocModal(false); load() }}
        />
      )}
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

  // Aplica los campos extraídos por la IA al formulario (el usuario luego revisa).
  const applyExtracted = (fields) => {
    if (fields.data) setData((d) => ({ ...d, ...fields.data }))
    if (fields.content != null) setContent(fields.content)
    if (fields.title) setTitle(fields.title)
  }

  const Icon = category.icon

  return (
    <Modal onClose={onClose} title={category.label} icon={Icon}>
      <ExtractBar category={category.id} onExtracted={applyExtracted} />

      {isPagos ? (
        <PagosForm data={data} setData={setData} content={content} setContent={setContent} />
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

// Normaliza data.cuentas (o migra campos sueltos viejos a una cuenta default).
function readAccounts(data) {
  if (Array.isArray(data.cuentas) && data.cuentas.length) return data.cuentas
  if (data.titular || data.banco || data.cbu || data.alias) {
    return [{
      titular: data.titular || '', banco: data.banco || '', cbu: data.cbu || '',
      alias: data.alias || '', moneda: data.moneda || 'ARS', default: true,
    }]
  }
  return []
}

function PagosForm({ data, setData, content, setContent }) {
  const MEDIOS = ['Efectivo', 'Tarjeta de crédito/débito', 'Transferencia bancaria', 'Mercado Pago']
  const selected = data.medios || []
  const cuentas = readAccounts(data)

  const toggleMedio = (m) => {
    const next = selected.includes(m) ? selected.filter((x) => x !== m) : [...selected, m]
    setData({ ...data, medios: next })
  }

  const setCuentas = (next) => {
    // Garantizar exactamente una default.
    if (next.length && !next.some((c) => c.default)) next[0].default = true
    setData({ ...data, cuentas: next })
  }
  const updateCuenta = (i, k, v) => setCuentas(cuentas.map((c, idx) => (idx === i ? { ...c, [k]: v } : c)))
  const setDefault = (i) => setCuentas(cuentas.map((c, idx) => ({ ...c, default: idx === i })))
  const addCuenta = () =>
    setCuentas([...cuentas, { titular: '', banco: '', cbu: '', alias: '', moneda: 'ARS', default: cuentas.length === 0 }])
  const removeCuenta = (i) => setCuentas(cuentas.filter((_, idx) => idx !== i))

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
        <Label>Cuentas bancarias para transferencia</Label>
        {cuentas.length === 0 && (
          <p className="mb-2 text-sm text-slatey">Agregá al menos una cuenta. La marcada como principal es la que ofrecerá el agente.</p>
        )}
        <div className="space-y-3">
          {cuentas.map((c, i) => (
            <div key={i} className={`rounded-xl border p-3 ${c.default ? 'border-hilton-300 bg-hilton-50/40' : 'border-hilton-100'}`}>
              <div className="mb-2 flex items-center justify-between">
                <button
                  type="button" onClick={() => setDefault(i)}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition ${
                    c.default ? 'bg-hilton-600 text-white' : 'border border-hilton-200 text-slatey hover:bg-mist'
                  }`}
                >
                  {c.default ? '★ Principal' : 'Marcar como principal'}
                </button>
                <button type="button" onClick={() => removeCuenta(i)} className="text-slatey hover:text-red-600">
                  <X size={15} />
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Field label="Titular" value={c.titular} onChange={(v) => updateCuenta(i, 'titular', v)} />
                <Field label="Banco" value={c.banco} onChange={(v) => updateCuenta(i, 'banco', v)} />
                <Field label="CBU" value={c.cbu} onChange={(v) => updateCuenta(i, 'cbu', v)} />
                <Field label="Alias" value={c.alias} onChange={(v) => updateCuenta(i, 'alias', v)} />
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-ink">Moneda</span>
                  <select
                    value={c.moneda || 'ARS'} onChange={(e) => updateCuenta(i, 'moneda', e.target.value)}
                    className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
                  >
                    <option value="ARS">Pesos (ARS)</option>
                    <option value="USD">Dólares (USD)</option>
                  </select>
                </label>
              </div>
            </div>
          ))}
        </div>
        <button onClick={addCuenta} className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-hilton-600 hover:text-hilton-700">
          <Plus size={15} /> Agregar cuenta
        </button>
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
    phone: place.phone || '',
    whatsapp: place.whatsapp || '',
    discount: place.discount || '',
    is_partner: place.is_partner || false,
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

        {/* Comercio amigo: acuerdo con descuento + contacto que el agente recomienda */}
        <div className="rounded-xl border border-hilton-100 bg-hilton-50/40 p-4">
          <label className="flex cursor-pointer items-center gap-2.5">
            <input
              type="checkbox" checked={form.is_partner}
              onChange={(e) => set('is_partner', e.target.checked)}
              className="h-4 w-4 rounded border-hilton-300 text-hilton-600 focus:ring-hilton-500"
            />
            <span className="text-sm font-medium text-ink">Es comercio amigo (con acuerdo)</span>
          </label>
          {form.is_partner && (
            <div className="mt-4 space-y-3">
              <Field label="Descuento para huéspedes" value={form.discount} onChange={(v) => set('discount', v)} placeholder="Ej: 15% en efectivo" />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Teléfono" value={form.phone} onChange={(v) => set('phone', v)} placeholder="+54 294 …" />
                <Field label="WhatsApp" value={form.whatsapp} onChange={(v) => set('whatsapp', v)} placeholder="5492944000000" />
              </div>
              <p className="text-xs text-slatey">El agente recomendará este comercio con su descuento y contacto.</p>
            </div>
          )}
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
// Barra "Completar desde documento": sube PDF o pega texto → IA extrae campos.
// El usuario revisa SIEMPRE antes de guardar.
// ───────────────────────────────────────────────────────────────────────────
function ExtractBar({ category, onExtracted }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('pdf')
  const [file, setFile] = useState(null)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const run = async () => {
    setLoading(true); setError(''); setDone(false)
    try {
      const payload = { category }
      if (mode === 'pdf') {
        if (!file) { setError('Elegí un archivo.'); setLoading(false); return }
        payload.file = file
      } else {
        if (!text.trim()) { setError('Pegá el texto.'); setLoading(false); return }
        payload.text = text
      }
      const { fields } = await extractFromDocument(payload)
      onExtracted(fields)
      setDone(true)
      setTimeout(() => { setOpen(false); setDone(false); setFile(null); setText('') }, 1200)
    } catch (e) {
      setError(e?.response?.data?.detail || 'No pude extraer datos. Cargalos a mano.')
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mb-4 inline-flex items-center gap-2 rounded-xl border border-hilton-200 bg-hilton-50/50 px-3.5 py-2 text-sm font-medium text-hilton-700 transition hover:bg-hilton-50"
      >
        <Wand2 size={15} /> Completar desde un documento
      </button>
    )
  }

  return (
    <div className="mb-4 rounded-2xl border border-hilton-200 bg-hilton-50/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-hilton-700">
          <Sparkles size={15} /> Completar desde documento
        </span>
        <button onClick={() => setOpen(false)} className="text-slatey hover:text-ink"><X size={16} /></button>
      </div>

      <div className="mb-3 flex gap-1 rounded-xl bg-white p-1">
        {[['pdf', 'Subir archivo'], ['text', 'Pegar texto']].map(([id, label]) => (
          <button
            key={id} onClick={() => setMode(id)}
            className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              mode === id ? 'bg-hilton-600 text-white' : 'text-slatey'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'pdf' ? (
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-hilton-300 bg-white px-4 py-3 text-sm text-slatey hover:bg-hilton-50">
          <Upload size={16} />
          {file ? file.name : 'Elegí un archivo (PDF o .md)…'}
          <input type="file" accept=".pdf,.md,.markdown,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" />
        </label>
      ) : (
        <textarea
          value={text} onChange={(e) => setText(e.target.value)} rows={4}
          placeholder="Pegá el texto del documento…"
          className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
        />
      )}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {done && <p className="mt-2 text-sm text-green-600">✓ Campos completados. Revisalos antes de guardar.</p>}

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={run} disabled={loading}
          className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />}
          {loading ? 'Leyendo…' : 'Extraer datos'}
        </button>
        <span className="text-xs text-slatey">La IA completa los campos; revisalos antes de guardar.</span>
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Modal de documento libre (PDF o texto pegado)
// ───────────────────────────────────────────────────────────────────────────
function DocumentModal({ categories, onClose, onSaved }) {
  const [mode, setMode] = useState('pdf')   // 'pdf' | 'text'
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState(categories[0].id)
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    if (!title.trim()) { setError('Poné un título.'); return }
    setSaving(true); setError('')
    try {
      if (mode === 'pdf') {
        if (!file) { setError('Elegí un archivo.'); setSaving(false); return }
        await uploadKnowledgeDocument({ title, category, file })
      } else {
        if (!text.trim()) { setError('Pegá el texto.'); setSaving(false); return }
        await uploadKnowledgeTextDocument({ title, category, text })
      }
      onSaved()
    } catch (e) {
      setError(e?.response?.data?.detail || 'No se pudo guardar.')
      setSaving(false)
    }
  }

  return (
    <Modal onClose={onClose} title="Nuevo documento" icon={FileUp}>
      <div className="space-y-4">
        <div className="flex gap-1 rounded-xl bg-mist p-1">
          {[['pdf', 'Subir archivo'], ['text', 'Pegar texto']].map(([id, label]) => (
            <button
              key={id} onClick={() => setMode(id)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                mode === id ? 'bg-white text-hilton-700 shadow-card' : 'text-slatey'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <Field label="Título" value={title} onChange={setTitle} placeholder="Ej: Reglamento interno" />

        <div>
          <Label>Tema</Label>
          <select
            value={category} onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
          >
            {categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </div>

        {mode === 'pdf' ? (
          <div>
            <Label>Archivo (PDF o Markdown)</Label>
            <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-hilton-300 px-4 py-3 text-sm text-slatey hover:bg-hilton-50">
              <Upload size={16} />
              {file ? file.name : 'Elegí un archivo (PDF o .md)…'}
              <input
                type="file" accept=".pdf,.md,.markdown,.txt"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
            </label>
          </div>
        ) : (
          <div>
            <Label>Texto</Label>
            <textarea
              value={text} onChange={(e) => setText(e.target.value)} rows={6}
              placeholder="Pegá acá el contenido…"
              className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
          </div>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-6 flex items-center justify-end gap-3">
        <button onClick={onClose} className="text-sm font-medium text-slatey hover:text-ink">Cancelar</button>
        <button
          onClick={save} disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
        >
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Guardar
        </button>
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
