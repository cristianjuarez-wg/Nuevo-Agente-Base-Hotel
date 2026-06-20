import { Users, BedDouble, Mountain } from 'lucide-react'
import { MEDIA_BASE } from '../../services/api'

function formatARS(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

// Resuelve rutas relativas (/fotos/… o /media/…) a URL servible.
function resolveImg(url) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  // /fotos/* son assets de la landing; /media/* los sirve el backend.
  if (url.startsWith('/media')) return `${MEDIA_BASE}${url}`
  return url
}

/**
 * Tarjeta de habitación dentro del chat (Fase 2).
 * Props: card (objeto del backend), onAction(action)
 */
export default function RoomCard({ card, onAction }) {
  const nights = card.nights
  return (
    <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
      {/* Imagen con overlays */}
      <div className="relative aspect-[16/10] overflow-hidden bg-stone-100">
        <img
          src={resolveImg(card.image)}
          alt={`Habitación ${card.title} del Hampton by Hilton Bariloche`}
          loading="lazy"
          className="h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-ink/55 via-transparent to-transparent" />
        {nights != null && (
          <span className="absolute right-3 top-3 rounded-full bg-white/90 px-2.5 py-0.5 text-[11px] font-medium text-hilton-700 backdrop-blur">
            {nights} {nights === 1 ? 'noche' : 'noches'}
          </span>
        )}
        <h4 className="absolute bottom-2.5 left-3 font-display text-xl font-600 text-white drop-shadow">
          {card.title}
        </h4>
      </div>

      {/* Cuerpo */}
      <div className="p-3.5">
        {card.description && (
          <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-slatey">
            {card.description}
          </p>
        )}
        <ul className="flex flex-wrap gap-x-3.5 gap-y-1 text-[11px] text-slatey">
          {card.capacity != null && (
            <li className="inline-flex items-center gap-1">
              <Users size={13} className="text-timber-400" /> Hasta {card.capacity}
            </li>
          )}
          {card.bed_config && (
            <li className="inline-flex items-center gap-1">
              <BedDouble size={13} className="text-timber-400" /> {card.bed_config}
            </li>
          )}
          {card.view && (
            <li className="inline-flex items-center gap-1">
              <Mountain size={13} className="text-timber-400" /> {card.view}
            </li>
          )}
        </ul>

        <div className="mt-3 flex items-end justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-slatey">
              Total {nights ? `· ${nights} ${nights === 1 ? 'noche' : 'noches'}` : 'estadía'}
            </p>
            <p className="font-display text-lg font-700 leading-none text-ink tabular-nums">
              USD {Math.round(card.price_usd)}
            </p>
            <p className="text-[11px] tabular-nums text-slatey">
              ARS {formatARS(card.price_ars)}
              {card.price_usd_night ? ` · USD ${Math.round(card.price_usd_night)}/noche` : ''}
            </p>
          </div>
        </div>

        {card.action && (
          <button
            onClick={() => onAction?.(card.action)}
            className="mt-3 w-full rounded-xl bg-hilton-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 active:scale-[0.99]"
          >
            {card.action.label}
          </button>
        )}
      </div>
    </div>
  )
}
