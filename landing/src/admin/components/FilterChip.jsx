// Chip de filtro unificado del backoffice: un solo lenguaje visual (activo en hilton-600,
// inactivo blanco con ring). Reemplaza las pills heterogéneas (azul/verde) que se veían
// recargadas. Lo usan TicketsView y LeadsView para que los filtros sean consistentes.
export function FilterChip({ active, onClick, label, count, icon: Icon }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition ${
        active
          ? 'bg-hilton-600 text-white shadow-card'
          : 'bg-white text-slatey ring-1 ring-mist hover:bg-mist'
      }`}
    >
      {Icon && <Icon size={13} />}
      {label}
      {count != null && <span className="tabular-nums opacity-70">({count})</span>}
    </button>
  )
}

// Etiqueta corta para nombrar cada grupo de chips (Estado / Área / Temperatura) sin recurrir
// a otro color: jerarquía por tipografía, no por acento.
export function FilterGroupLabel({ children }) {
  return <span className="text-[11px] font-medium uppercase tracking-wide text-slatey">{children}</span>
}

// Divisor sutil entre grupos de filtros (oculto en mobile, donde los chips hacen wrap).
export function FilterDivider() {
  return <span className="mx-1 hidden h-5 w-px bg-mist sm:block" />
}
