import { UtensilsCrossed, ArrowRight } from 'lucide-react'
import { getStrings } from '../../i18n/chat'

/**
 * Tarjeta del restaurante dentro del chat (Fase 2).
 * Muestra la carta de PLAZA con un botón que abre la pantalla de carrito (#pedido).
 * Props: card (objeto del backend con action.open_url), onAction(action), lang
 */
export default function MenuCard({ card, onAction, lang = 'es' }) {
  const t = getStrings(lang)
  // El backend manda la card en español; localizamos los textos visibles y la acción.
  const action = card.action
    ? { ...card.action, label: t.viewMenu }
    : null

  return (
    <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-card">
      <div className="flex items-start gap-3 p-3.5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-timber-50 text-timber-500">
          <UtensilsCrossed size={20} />
        </div>
        <div className="min-w-0">
          <h4 className="font-display text-base font-600 leading-tight text-ink">
            {card.title || t.menuTitle}
          </h4>
          <p className="mt-0.5 text-xs leading-relaxed text-slatey">
            {card.description || t.menuDesc}
          </p>
        </div>
      </div>

      {action && (
        <div className="px-3.5 pb-3.5">
          <button
            onClick={() => onAction?.(action)}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-hilton-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 active:scale-[0.99]"
          >
            {action.label} <ArrowRight size={15} />
          </button>
        </div>
      )}
    </div>
  )
}
