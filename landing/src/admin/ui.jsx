import { Loader2, Bot, Globe, User, MessageCircle } from 'lucide-react'

// Formato unificado (única fuente de verdad en lib/format.js).
export { formatNumber, formatUSD, formatARS, formatDate, formatDateTime } from '../lib/format'

export function PageHeader({ title, subtitle, right }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-serif text-2xl font-700 text-ink sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slatey">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function StatCard({ icon: Icon, label, value, tone = 'hilton' }) {
  const tones = {
    hilton: 'bg-hilton-50 text-hilton-600',
    green: 'bg-green-50 text-green-600',
    amber: 'bg-amber-50 text-amber-600',
    red: 'bg-red-50 text-red-600',
  }
  return (
    <div className="flex items-center gap-4 rounded-2xl bg-white p-5 shadow-card">
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}>
        {Icon && <Icon size={22} />}
      </div>
      <div className="min-w-0">
        <p className="font-serif text-2xl font-700 tabular-nums text-ink">{value}</p>
        <p className="truncate text-xs text-slatey">{label}</p>
      </div>
    </div>
  )
}

export function Badge({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-mist text-slatey',
    green: 'bg-green-100 text-green-700',
    amber: 'bg-amber-100 text-amber-700',
    red: 'bg-red-100 text-red-700',
    blue: 'bg-hilton-100 text-hilton-700',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  )
}

// Indicador sutil de "tenemos contacto por WhatsApp". El backend (whatsapp_linked) lo
// marca cuando la persona NOS ESCRIBIÓ por WhatsApp (dato real, no heurística) — o,
// para el equipo, porque asumimos que su número es WhatsApp. Significa que ese es un
// canal de comunicación efectivo; si no aparece, conviene usar otro medio.
export function WhatsAppDot({ linked, title = 'Tenemos contacto por WhatsApp', className = '' }) {
  if (!linked) return null
  return (
    <span title={title} className={`inline-flex shrink-0 ${className}`}>
      <MessageCircle size={13} className="text-green-500/80" aria-label={title} />
    </span>
  )
}

// Origen unificado de una reserva/lead/pasajero. El icono Bot marca que intervino la IA
// (Aura); Globe = el huésped reservó solo en el sitio; User = carga manual del equipo.
// Recibe la `key` que ya resuelve el backend (origin.key). Mismo look en todo el backoffice.
const ORIGIN_MAP = {
  aura_whatsapp: { tone: 'green', icon: Bot, label: 'WhatsApp' },
  aura_web: { tone: 'blue', icon: Bot, label: 'ChatWeb' },
  web: { tone: 'gray', icon: Globe, label: 'Sitio web' },
  manual: { tone: 'amber', icon: User, label: 'Manual' },
}

export function OriginBadge({ origin }) {
  // Acepta el objeto origin completo o solo la key.
  const key = typeof origin === 'string' ? origin : origin?.key
  const o = ORIGIN_MAP[key] || ORIGIN_MAP.web
  const Icon = o.icon
  const label = (typeof origin === 'object' && origin?.label) || o.label
  return (
    <Badge tone={o.tone}>
      <Icon size={11} className="mr-1" /> {label}
    </Badge>
  )
}

export function Loading({ label = 'Cargando…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slatey">
      <Loader2 size={18} className="animate-spin" />
      {label}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, desc }) {
  return (
    <div className="rounded-2xl border border-dashed border-hilton-200 bg-white py-16 text-center">
      {Icon && <Icon size={32} className="mx-auto mb-3 text-slatey" />}
      <p className="font-serif text-lg font-600 text-ink">{title}</p>
      {desc && <p className="mt-1 text-sm text-slatey">{desc}</p>}
    </div>
  )
}

/** Tabla responsive: tabla en desktop, cards en mobile.
 *  Orden por columna OPCIONAL: una columna con `sortable: true` (y `sortKey`, default `key`)
 *  muestra una flecha y dispara `onSort(sortKey)`. `sort` = { key, dir } resalta la activa. */
export function ResponsiveTable({ columns, rows, renderCard, sort, onSort }) {
  return (
    <>
      {/* Desktop */}
      <div className="hidden overflow-hidden rounded-2xl bg-white shadow-card md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-mist bg-mist/50 text-xs uppercase tracking-wide text-slatey">
              {columns.map((c) => {
                const sortKey = c.sortKey || c.key
                const active = sort?.key === sortKey
                const arrow = !c.sortable ? '' : active ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ' ↕'
                return (
                  <th key={c.key} className="px-4 py-3 font-semibold">
                    {c.sortable && onSort ? (
                      <button
                        onClick={() => onSort(sortKey)}
                        className={`inline-flex items-center transition hover:text-ink ${active ? 'text-hilton-700' : ''}`}
                      >
                        {c.label}<span className="tabular-nums opacity-60">{arrow}</span>
                      </button>
                    ) : c.label}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row._key ?? i} className="border-b border-mist/60 last:border-0 hover:bg-hilton-50/40">
                {columns.map((c) => (
                  <td key={c.key} className="px-4 py-3.5 align-middle">
                    {c.render ? c.render(row) : row[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile */}
      <div className="space-y-3 md:hidden">
        {rows.map((row, i) => (
          <div key={row._key ?? i} className="rounded-2xl bg-white p-4 shadow-card">
            {renderCard(row)}
          </div>
        ))}
      </div>
    </>
  )
}
