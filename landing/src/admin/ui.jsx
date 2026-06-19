import { Loader2 } from 'lucide-react'

export function formatARS(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

export function formatDate(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return iso
  }
}

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

/** Tabla responsive: tabla en desktop, cards en mobile. */
export function ResponsiveTable({ columns, rows, renderCard }) {
  return (
    <>
      {/* Desktop */}
      <div className="hidden overflow-hidden rounded-2xl bg-white shadow-card md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-mist bg-mist/50 text-xs uppercase tracking-wide text-slatey">
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-3 font-semibold">{c.label}</th>
              ))}
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
