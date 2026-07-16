// Chip de filtro unificado del backoffice: un solo lenguaje visual (activo en hilton-600,
// inactivo blanco con ring). Reemplaza las pills heterogéneas (azul/verde) que se veían
// recargadas. Lo usan TicketsView y LeadsView para que los filtros sean consistentes.
// `iconOnly`: muestra solo el ícono + el contador, sin el texto del label (para chips cuyo
// ícono ya es inequívoco, ej. canales WhatsApp/Instagram). El label se conserva como
// title/aria-label para hover y lectores de pantalla. Sin `iconOnly` el comportamiento es
// el de siempre (texto + ícono), así los consumidores actuales no cambian.
export function FilterChip({ active, onClick, label, count, icon: Icon, iconOnly = false, iconClassName = '' }) {
  return (
    <button
      onClick={onClick}
      title={iconOnly ? label : undefined}
      aria-label={iconOnly ? label : undefined}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full py-1.5 text-xs font-medium transition ${
        iconOnly ? 'px-2.5' : 'px-3'
      } ${
        active
          ? 'bg-hilton-600 text-white shadow-card'
          : 'bg-white text-slatey ring-1 ring-mist hover:bg-mist'
      }`}
    >
      {/* El color de marca del ícono (WhatsApp verde, IG rosa…) solo se aplica cuando el chip
          está INACTIVO: activo el fondo es hilton-600 y el ícono va blanco para contraste. */}
      {Icon && <Icon size={13} className={active ? '' : iconClassName} />}
      {!iconOnly && label}
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
