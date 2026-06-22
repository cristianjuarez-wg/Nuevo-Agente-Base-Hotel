import { Leaf, WheatOff } from 'lucide-react'

// Categorías de la carta (orden de presentación). Compartido por la pantalla #pedido
// y la card interactiva del chat.
export const CATEGORIES = [
  { id: 'tapas', label: 'Tapas' },
  { id: 'plato', label: 'Platos' },
  { id: 'sandwich', label: 'Sándwiches' },
  { id: 'ensalada', label: 'Ensaladas' },
  { id: 'pizza', label: 'Pizzas' },
  { id: 'postre', label: 'Postres' },
  { id: 'cerveza', label: 'Cervezas' },
  { id: 'trago', label: 'Tragos' },
  { id: 'vino', label: 'Vinos' },
  { id: 'cafeteria', label: 'Café' },
  { id: 'merienda', label: 'Merienda' },
]

// Imagen de respaldo cuando un plato no tiene foto cargada.
export const MENU_FALLBACK_IMG =
  'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80'

// Badge de atributo dietético del plato (veggie / vegano / sin TACC).
export function TagBadge({ tag }) {
  const map = {
    vegetariano: { icon: Leaf, label: 'Veggie', cls: 'bg-forest-50 text-forest-600' },
    vegano: { icon: Leaf, label: 'Vegano', cls: 'bg-forest-50 text-forest-600' },
    sin_tacc: { icon: WheatOff, label: 'Sin TACC', cls: 'bg-amber-50 text-amber-700' },
  }
  const t = map[tag]
  if (!t) return null
  const Icon = t.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${t.cls}`}>
      <Icon size={10} /> {t.label}
    </span>
  )
}
