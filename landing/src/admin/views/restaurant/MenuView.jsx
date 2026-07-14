import { useState, useEffect } from 'react'
import { UtensilsCrossed, Plus, Pencil, Trash2, ToggleLeft, ToggleRight, X, Save, Loader2, Moon, AlertTriangle } from 'lucide-react'
import { listMenuAdmin, saveMenuItem, patchMenuStatus, deleteMenuItem } from '../../../services/api'
import { PageHeader, Badge, Loading, EmptyState, formatUSD, formatARS } from '../../ui'
import ImageInput from '../../components/ImageInput'
import { toast } from '../../toast'
import SearchInput from '../../components/SearchInput'

const CATEGORIES = [
  'tapas', 'plato', 'sandwich', 'ensalada', 'pizza', 'postre',
  'cerveza', 'trago', 'vino', 'cafeteria', 'merienda', 'bebida',
]
const TAG_OPTIONS = ['vegetariano', 'vegano', 'sin_tacc', 'picante']
const ALLERGEN_OPTIONS = ['gluten', 'lacteos', 'frutos_secos', 'huevo', 'pescado', 'mariscos']

export default function MenuView() {
  const [items, setItems] = useState([])
  const [rate, setRate] = useState(null)
  const [loading, setLoading] = useState(true)
  const [edit, setEdit] = useState(null)        // null=cerrado, {}=nuevo, {...}=editar
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [query, setQuery] = useState('')

  const load = (silent = false) => {
    if (!silent) setLoading(true)
    listMenuAdmin()
      .then((d) => { setItems(d.menu || []); setRate(d.exchange_rate || null) })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const toggle = async (it) => {
    const next = it.status === 'active' ? 'inactive' : 'active'
    try { await patchMenuStatus(it.id, next); load(true); toast.success(next === 'active' ? 'Plato activado' : 'Plato desactivado') }
    catch { toast.error('No se pudo cambiar el estado') }
  }

  const handleDelete = async (it) => {
    try { await deleteMenuItem(it.id); setConfirmDelete(null); load(true); toast.success('Plato eliminado') }
    catch { toast.error('No se pudo eliminar') }
  }

  if (loading) return <Loading label="Cargando la carta…" />

  const q = query.trim().toLowerCase()
  const filtered = q ? items.filter((i) => i.name.toLowerCase().includes(q) || (i.category || '').includes(q)) : items

  return (
    <div>
      <PageHeader
        title="Carta del restaurante"
        subtitle={rate ? `Precios en USD. El ARS se calcula con la cotización vigente (${formatARS(rate.rate)}).` : 'Gestioná los platos del restaurante PLAZA.'}
        right={
          <button onClick={() => setEdit({})} className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700">
            <Plus size={16} /> Nuevo plato
          </button>
        }
      />

      <div className="mb-4"><SearchInput value={query} onChange={setQuery} placeholder="Buscar por nombre o categoría…" /></div>

      {filtered.length === 0 ? (
        <EmptyState icon={UtensilsCrossed} title="Sin platos" desc="Agregá el primer plato de la carta." />
      ) : (
        <div className="space-y-2.5">
          {filtered.map((it) => (
            <div key={it.id} className={`flex items-center gap-4 rounded-2xl border border-hilton-100 bg-white p-3 shadow-card ${it.status === 'inactive' ? 'opacity-60' : ''}`}>
              {it.image_url && <img src={it.image_url} alt={it.name} className="h-14 w-14 shrink-0 rounded-xl object-cover" />}
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-ink">{it.name}</span>
                  <Badge tone="gray">{it.category}</Badge>
                  {(it.tags || []).map((t) => <Badge key={t} tone="green">{t}</Badge>)}
                  {it.only_dinner && <Badge tone="blue"><Moon size={11} className="mr-1" /> Solo cena</Badge>}
                  {!it.available && <Badge tone="amber">sin stock</Badge>}
                </div>
                {it.allergens?.length > 0 && (
                  <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-red-600">
                    <AlertTriangle size={11} /> Contiene: {it.allergens.join(', ')}
                  </p>
                )}
                {it.description && <p className="mt-0.5 line-clamp-1 text-xs text-slatey">{it.description}</p>}
              </div>
              <span className="shrink-0 text-sm font-semibold tabular-nums text-hilton-700">{formatUSD(it.price_usd)}<span className="ml-1 font-normal text-slatey">/ {formatARS(it.price_ars)}</span></span>
              <div className="flex shrink-0 items-center gap-1">
                <button onClick={() => toggle(it)} title={it.status === 'active' ? 'Desactivar' : 'Activar'} className={`rounded-lg p-2 transition ${it.status === 'active' ? 'bg-forest-100 text-forest-600 hover:bg-forest-200' : 'text-slatey/50 hover:bg-mist'}`}>
                  {it.status === 'active' ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                </button>
                <button onClick={() => setEdit(it)} title="Editar" className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink"><Pencil size={15} /></button>
                <button onClick={() => setConfirmDelete(it)} title="Eliminar" className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600"><Trash2 size={15} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {edit !== null && <MenuModal item={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(true); toast.success('Plato guardado') }} />}
      {confirmDelete && <ConfirmModal title={`¿Eliminar "${confirmDelete.name}"?`} onCancel={() => setConfirmDelete(null)} onConfirm={() => handleDelete(confirmDelete)} />}
    </div>
  )
}

function MenuModal({ item, onClose, onSaved }) {
  const isNew = !item.id
  const [name, setName] = useState(item.name || '')
  const [description, setDescription] = useState(item.description || '')
  const [category, setCategory] = useState(item.category || 'plato')
  const [priceUsd, setPriceUsd] = useState(item.price_usd ?? '')
  const [image, setImage] = useState(item.image_url || '')
  const [tags, setTags] = useState(item.tags || [])
  const [allergens, setAllergens] = useState(item.allergens || [])
  const [available, setAvailable] = useState(item.available !== false)
  const [onlyDinner, setOnlyDinner] = useState(!!item.only_dinner)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const toggleIn = (arr, set, v) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])

  const save = async () => {
    if (!name.trim()) { setError('El nombre es obligatorio.'); return }
    if (priceUsd === '' || isNaN(Number(priceUsd))) { setError('Ingresá un precio USD válido.'); return }
    setSaving(true); setError('')
    try {
      await saveMenuItem({
        name: name.trim(), description: description.trim() || null, category,
        price_usd: Number(priceUsd), image_url: image || null,
        tags, allergens, available, only_dinner: onlyDinner, status: item.status || 'active',
      }, item.id)
      onSaved()
    } catch { setError('No se pudo guardar.'); setSaving(false) }
  }

  return (
    <Modal title={isNew ? 'Nuevo plato' : 'Editar plato'} onClose={onClose}>
      <div className="space-y-4">
        <Field label="Nombre *" value={name} onChange={setName} placeholder="Ej: Trucha de Alicurá" />
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Descripción</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Categoría</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-ink">Precio USD *</span>
            <input type="number" min="0" step="0.01" value={priceUsd} onChange={(e) => setPriceUsd(e.target.value)} className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100" />
          </label>
        </div>
        <div>
          <span className="mb-1.5 block text-sm font-medium text-ink">Aptos / tags</span>
          <div className="flex flex-wrap gap-2">
            {TAG_OPTIONS.map((t) => (
              <button key={t} onClick={() => toggleIn(tags, setTags, t)} className={`rounded-full px-3 py-1 text-xs transition ${tags.includes(t) ? 'bg-forest-500 text-white' : 'bg-mist text-slatey hover:bg-stone-200'}`}>{t}</button>
            ))}
          </div>
        </div>
        <div>
          <span className="mb-1.5 block text-sm font-medium text-ink">Alérgenos</span>
          <div className="flex flex-wrap gap-2">
            {ALLERGEN_OPTIONS.map((a) => (
              <button key={a} onClick={() => toggleIn(allergens, setAllergens, a)} className={`rounded-full px-3 py-1 text-xs transition ${allergens.includes(a) ? 'bg-amber-500 text-white' : 'bg-mist text-slatey hover:bg-stone-200'}`}>{a}</button>
            ))}
          </div>
        </div>
        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} className="h-4 w-4 rounded border-hilton-300 text-hilton-600" /> Hay stock</label>
          <label className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={onlyDinner} onChange={(e) => setOnlyDinner(e.target.checked)} className="h-4 w-4 rounded border-hilton-300 text-hilton-600" /> Solo cena</label>
        </div>
        <div>
          <span className="mb-1 block text-sm font-medium text-ink">Foto</span>
          <ImageInput value={image} onChange={setImage} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">Cancelar</button>
          <button onClick={save} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
          </button>
        </div>
      </div>
    </Modal>
  )
}

function ConfirmModal({ title, onCancel, onConfirm }) {
  const [deleting, setDeleting] = useState(false)
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="mb-6 text-sm text-slatey">Esta acción no se puede deshacer.</p>
      <div className="flex justify-end gap-3">
        <button onClick={onCancel} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">Cancelar</button>
        <button onClick={async () => { setDeleting(true); await onConfirm() }} disabled={deleting} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-60">
          {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} Eliminar
        </button>
      </div>
    </Modal>
  )
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">{title}</h3>
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
      <input type="text" value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100" />
    </label>
  )
}
