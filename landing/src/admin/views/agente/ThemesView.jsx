import { useState, useEffect } from 'react'
import { Palette, Plus, Pencil, Trash2, X, Save, Loader2, Pin, ToggleLeft, ToggleRight, AlertTriangle } from 'lucide-react'
import { listChatThemes, saveChatTheme, patchChatThemeStatus, deleteChatTheme } from '../../../services/api'
import { PageHeader, Badge, Loading, EmptyState } from '../../ui'

const MONTHS = [
  '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

const STATUS_OPTIONS = [
  { value: 'active', label: 'Activo (por fechas)' },
  { value: 'pinned', label: 'Fijado (siempre activo)' },
  { value: 'inactive', label: 'Inactivo' },
]

const EFFECT_OPTIONS = [
  { value: 'none', label: 'Sin efecto' },
  { value: 'snow', label: '❄️ Nieve cayendo' },
  { value: 'snow_gold', label: '✨ Nieve + destellos dorados' },
  { value: 'leaves', label: '🍃 Destellos flotando' },
  { value: 'bunny', label: '🐰 Conejito asomándose' },
]

function statusBadge(s) {
  if (s === 'pinned') return <Badge tone="hilton">fijado</Badge>
  if (s === 'active') return <Badge tone="green">activo</Badge>
  return <Badge tone="gray">inactivo</Badge>
}

function rangeLabel(t) {
  if (!t.active_from_month || !t.active_until_month) return 'Sin rango (siempre)'
  const from = `${MONTHS[t.active_from_month]} ${t.active_from_day}`
  const until = `${MONTHS[t.active_until_month]} ${t.active_until_day}`
  return `${from} → ${until}`
}

// ¿Hoy cae dentro del rango mes/día del tema? (misma lógica que el backend)
function isInSeason(t) {
  const fm = t.active_from_month, fd = t.active_from_day
  const um = t.active_until_month, ud = t.active_until_day
  if (!fm || !fd || !um || !ud) return true   // sin rango = siempre
  const now = new Date()
  const start = fm * 100 + fd
  const end = um * 100 + ud
  const today = (now.getMonth() + 1) * 100 + now.getDate()
  return start <= end
    ? today >= start && today <= end
    : today >= start || today <= end          // rango que cruza el año nuevo
}

// Preview minimalista del tema — simula el header del chat
function ThemePreview({ theme }) {
  const hBg = theme.header_bg || '#003f77'
  const hText = theme.header_text || '#ffffff'
  const accent = theme.accent_color || '#005aa9'
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-hilton-100" style={{ width: 160 }}>
      <div className="flex items-center gap-2 px-3 py-2" style={{ background: hBg, color: hText }}>
        <span style={{ fontSize: 16 }}>{theme.emoji || '💬'}</span>
        <span style={{ fontSize: 11, fontWeight: 600 }}>Aura</span>
      </div>
      <div className="bg-white px-3 py-2 space-y-1.5">
        <div className="h-2 w-20 rounded-full" style={{ background: '#f0f0f0' }} />
        <div className="h-2 w-14 rounded-full ml-auto" style={{ background: accent }} />
        <div className="h-2 w-16 rounded-full" style={{ background: '#f0f0f0' }} />
      </div>
    </div>
  )
}

export default function ThemesView() {
  const [themes, setThemes] = useState([])
  const [loading, setLoading] = useState(true)
  const [editTheme, setEditTheme] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null)

  const load = (silent = false) => {
    if (!silent) setLoading(true)
    listChatThemes()
      .then((t) => setThemes(t || []))
      .catch(() => setThemes([]))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const cycleStatus = async (theme) => {
    const next = theme.status === 'inactive' ? 'active' : theme.status === 'active' ? 'pinned' : 'inactive'
    await patchChatThemeStatus(theme.id, next)
    load(true)
  }

  const handleDelete = async (theme) => {
    await deleteChatTheme(theme.id)
    setConfirmDelete(null)
    load()
  }

  if (loading) return <Loading label="Cargando temas…" />

  return (
    <div>
      <PageHeader
        title="Temas del chat"
        subtitle="Personalizá los colores del widget de Aura según la época del año: Navidad, ski, verano y más."
        right={
          <button
            onClick={() => setEditTheme({})}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700"
          >
            <Plus size={16} /> Nuevo tema
          </button>
        }
      />

      <div className="mb-4 rounded-xl bg-hilton-50 border border-hilton-100 px-4 py-3 text-sm text-hilton-700">
        <strong>Prioridad:</strong> Un tema <em>fijado</em> siempre anula los demás. Si no hay fijado, se activa el que coincide con la fecha de hoy. Solo puede haber un tema activo a la vez.
      </div>

      {themes.length === 0 ? (
        <EmptyState
          icon={Palette}
          title="Aún no hay temas"
          desc="Creá el primer tema estacional y el chat cambiará de look automáticamente en esa época."
        />
      ) : (
        <div className="space-y-3">
          {themes.map((t) => (
            <div
              key={t.id}
              className="flex flex-col gap-3 rounded-2xl border border-hilton-100 bg-white p-4 shadow-card sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="flex gap-4 flex-1 min-w-0">
                <ThemePreview theme={t} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="text-xl">{t.emoji || '💬'}</span>
                    <span className="font-semibold text-ink">{t.name}</span>
                    {statusBadge(t.status)}
                  </div>
                  {t.description && (
                    <p className="text-sm text-slatey line-clamp-2 mb-1">{t.description}</p>
                  )}
                  <p className="text-xs text-slatey/70">{rangeLabel(t)}</p>
                  {t.status === 'active' && !isInSeason(t) && (
                    <p className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-700">
                      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                      <span>Activo pero fuera de su temporada: no se muestra hoy. Usá <strong>Fijar</strong> para forzarlo ahora.</span>
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {[
                      { label: 'Header', color: t.header_bg },
                      { label: 'Acento', color: t.accent_color },
                      { label: 'FAB', color: t.fab_bg },
                    ].filter(c => c.color).map(c => (
                      <span key={c.label} className="inline-flex items-center gap-1 rounded-full border border-hilton-100 px-2 py-0.5 text-xs text-slatey">
                        <span className="inline-block h-3 w-3 rounded-full border border-black/10" style={{ background: c.color }} />
                        {c.label}
                      </span>
                    ))}
                    {t.effect && t.effect !== 'none' && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-hilton-50 px-2 py-0.5 text-xs text-hilton-700">
                        {EFFECT_OPTIONS.find(e => e.value === t.effect)?.label || t.effect}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => cycleStatus(t)}
                  title={t.status === 'inactive' ? 'Activar' : t.status === 'active' ? 'Fijar siempre' : 'Desactivar'}
                  className={`rounded-lg p-2 transition ${
                    t.status === 'pinned'
                      ? 'bg-hilton-100 text-hilton-700 hover:bg-hilton-200'
                      : t.status === 'active'
                      ? 'bg-forest-100 text-forest-600 hover:bg-forest-200'
                      : 'text-slatey/50 hover:bg-mist hover:text-slatey'
                  }`}
                >
                  {t.status === 'pinned'
                    ? <Pin size={18} fill="currentColor" />
                    : t.status === 'active'
                    ? <ToggleRight size={20} />
                    : <ToggleLeft size={20} />}
                </button>
                <button onClick={() => setEditTheme(t)} title="Editar" className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink">
                  <Pencil size={16} />
                </button>
                <button onClick={() => setConfirmDelete(t)} title="Eliminar" className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editTheme !== null && (
        <ThemeModal
          theme={editTheme}
          onClose={() => setEditTheme(null)}
          onSaved={() => { setEditTheme(null); load() }}
        />
      )}

      {confirmDelete && (
        <ConfirmModal
          title={`¿Eliminar "${confirmDelete.name}"?`}
          message="Esta acción no se puede deshacer."
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => handleDelete(confirmDelete)}
        />
      )}
    </div>
  )
}

// ── Modal de formulario ────────────────────────────────────────────────────

function ThemeModal({ theme, onClose, onSaved }) {
  const isNew = !theme.id
  const [name, setName] = useState(theme.name || '')
  const [emoji, setEmoji] = useState(theme.emoji || '')
  const [description, setDescription] = useState(theme.description || '')
  const [fromMonth, setFromMonth] = useState(theme.active_from_month ?? '')
  const [fromDay, setFromDay] = useState(theme.active_from_day ?? '')
  const [untilMonth, setUntilMonth] = useState(theme.active_until_month ?? '')
  const [untilDay, setUntilDay] = useState(theme.active_until_day ?? '')
  const [headerBg, setHeaderBg] = useState(theme.header_bg || '#003f77')
  const [headerText, setHeaderText] = useState(theme.header_text || '#ffffff')
  const [accentColor, setAccentColor] = useState(theme.accent_color || '#005aa9')
  const [bubbleBg, setBubbleBg] = useState(theme.bubble_bg || '#f7f4ee')
  const [fabBg, setFabBg] = useState(theme.fab_bg || '#003f77')
  const [fabText, setFabText] = useState(theme.fab_text || '#ffffff')
  const [effect, setEffect] = useState(theme.effect || 'none')
  const [status, setStatus] = useState(theme.status || 'active')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Preview en vivo
  const liveTheme = { emoji, header_bg: headerBg, header_text: headerText, accent_color: accentColor }

  const save = async () => {
    if (!name.trim()) { setError('El nombre es obligatorio.'); return }
    setSaving(true)
    setError('')
    try {
      await saveChatTheme({
        name: name.trim(),
        emoji: emoji.trim() || null,
        description: description.trim() || null,
        active_from_month: fromMonth ? parseInt(fromMonth) : null,
        active_from_day: fromDay ? parseInt(fromDay) : null,
        active_until_month: untilMonth ? parseInt(untilMonth) : null,
        active_until_day: untilDay ? parseInt(untilDay) : null,
        header_bg: headerBg || null,
        header_text: headerText || null,
        accent_color: accentColor || null,
        bubble_bg: bubbleBg || null,
        fab_bg: fabBg || null,
        fab_text: fabText || null,
        effect,
        status,
      }, theme.id)
      onSaved()
    } catch {
      setError('No se pudo guardar. Intentá de nuevo.')
      setSaving(false)
    }
  }

  return (
    <Modal title={isNew ? 'Nuevo tema' : 'Editar tema'} icon={Palette} onClose={onClose}>
      <div className="space-y-4">
        {/* Preview en vivo */}
        <div className="flex items-center gap-4 rounded-xl bg-mist p-3">
          <ThemePreview theme={liveTheme} />
          <p className="text-xs text-slatey">Vista previa del header del chat con los colores actuales.</p>
        </div>

        <div className="grid grid-cols-[1fr_80px] gap-3">
          <Field label="Nombre *" value={name} onChange={setName} placeholder="Ej: Navidad" />
          <Field label="Emoji" value={emoji} onChange={setEmoji} placeholder="🎄" />
        </div>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Descripción</span>
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)}
            rows={2} placeholder="Descripción interna del tema…"
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100 resize-none"
          />
        </label>

        {/* Rango de fechas */}
        <div>
          <p className="mb-2 text-sm font-medium text-ink">Rango de activación</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <p className="text-xs text-slatey">Desde</p>
              <MonthDay month={fromMonth} day={fromDay} onMonth={setFromMonth} onDay={setFromDay} />
            </div>
            <div className="space-y-2">
              <p className="text-xs text-slatey">Hasta</p>
              <MonthDay month={untilMonth} day={untilDay} onMonth={setUntilMonth} onDay={setUntilDay} />
            </div>
          </div>
          <p className="mt-1 text-xs text-slatey/70">El rango puede cruzar el año nuevo (ej: diciembre → enero).</p>
        </div>

        {/* Colores */}
        <div>
          <p className="mb-2 text-sm font-medium text-ink">Colores del tema</p>
          <div className="grid grid-cols-2 gap-3">
            <ColorField label="Header — fondo" value={headerBg} onChange={setHeaderBg} />
            <ColorField label="Header — texto/iconos" value={headerText} onChange={setHeaderText} />
            <ColorField label="Acento (burbujas usuario)" value={accentColor} onChange={setAccentColor} />
            <ColorField label="Burbujas del agente" value={bubbleBg} onChange={setBubbleBg} />
            <ColorField label="FAB — fondo" value={fabBg} onChange={setFabBg} />
            <ColorField label="FAB — texto/iconos" value={fabText} onChange={setFabText} />
          </div>
        </div>

        {/* Efecto animado */}
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Efecto animado</span>
          <select
            value={effect} onChange={(e) => setEffect(e.target.value)}
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
          >
            {EFFECT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <span className="mt-1 block text-xs text-slatey/70">
            Animación sutil sobre el chat. Se desactiva sola si el usuario tiene "reducir movimiento".
          </span>
        </label>

        {/* Estado */}
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Estado</span>
          <select
            value={status} onChange={(e) => setStatus(e.target.value)}
            className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
          >
            {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
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

// Selector mes + día
function MonthDay({ month, day, onMonth, onDay }) {
  return (
    <div className="flex gap-2">
      <select
        value={month} onChange={(e) => onMonth(e.target.value)}
        className="flex-1 rounded-xl border border-hilton-200 px-2 py-2 text-sm focus:border-hilton-500 focus:outline-none"
      >
        <option value="">Mes</option>
        {MONTHS.slice(1).map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
      </select>
      <input
        type="number" min="1" max="31" value={day} onChange={(e) => onDay(e.target.value)}
        placeholder="Día" className="w-16 rounded-xl border border-hilton-200 px-2 py-2 text-sm focus:border-hilton-500 focus:outline-none"
      />
    </div>
  )
}

// Campo de color con swatch
function ColorField({ label, value, onChange }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)}
          className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-hilton-200 p-0.5"
        />
        <input
          type="text" value={value || ''} onChange={(e) => onChange(e.target.value)}
          placeholder="#rrggbb"
          className="flex-1 rounded-xl border border-hilton-200 px-2.5 py-2 text-sm font-mono focus:border-hilton-500 focus:outline-none"
        />
      </div>
    </label>
  )
}

// ── Modal de confirmación ──────────────────────────────────────────────────

function ConfirmModal({ title, message, onCancel, onConfirm }) {
  const [deleting, setDeleting] = useState(false)
  const confirm = async () => { setDeleting(true); await onConfirm() }
  return (
    <Modal title={title} icon={Trash2} onClose={onCancel}>
      <p className="mb-6 text-sm text-slatey">{message}</p>
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
