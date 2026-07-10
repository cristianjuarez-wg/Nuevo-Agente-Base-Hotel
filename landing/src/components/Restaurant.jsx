import { useEffect, useState } from 'react'
import { UtensilsCrossed, Clock, ArrowRight, Leaf, WheatOff } from 'lucide-react'
import { listMenuPublic } from '../services/api'
import { formatUSD } from '../lib/format'
import { useBusinessProfile } from '../hooks/useBusinessProfile'
import Reveal, { RevealGroup, RevealItem } from './motion/Reveal'

const HERO = 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1600&q=80'

const CATS = [
  { id: 'tapas', label: 'Tapas' },
  { id: 'plato', label: 'Platos' },
  { id: 'pizza', label: 'Pizzas' },
  { id: 'postre', label: 'Postres' },
  { id: 'trago', label: 'Tragos' },
]

function Tag({ tag }) {
  const map = {
    vegetariano: { icon: Leaf, label: 'Veggie' },
    vegano: { icon: Leaf, label: 'Vegano' },
    sin_tacc: { icon: WheatOff, label: 'Sin TACC' },
  }
  const t = map[tag]
  if (!t) return null
  const Icon = t.icon
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-linen px-2 py-0.5 text-[10px] font-medium text-timber-600">
      <Icon size={10} /> {t.label}
    </span>
  )
}

export default function Restaurant() {
  const [menu, setMenu] = useState([])
  const [cat, setCat] = useState('tapas')
  const HOTEL = useBusinessProfile()
  // Nombre del restaurante desde el perfil del negocio (F3.3). Si trae un "—", lo partimos en
  // dos líneas (título · subtítulo) como el diseño original; si no, va en una sola línea.
  const restaurantName = HOTEL.restaurant_name || "Plaza — Hampton's Kitchen House"
  const [rName1, rName2] = restaurantName.split(/\s*—\s*/, 2)

  useEffect(() => {
    listMenuPublic().then(setMenu).catch(() => setMenu([]))
  }, [])

  const cats = CATS.filter((c) => menu.some((m) => m.category === c.id))
  const visible = menu.filter((m) => m.category === cat).slice(0, 6)

  return (
    <section id="restaurante" className="section-pad bg-stone-50">
      <div className="container-x">
        {/* Vitrina */}
        <Reveal>
          <div className="grid items-center gap-8 lg:grid-cols-2">
            <div className="relative overflow-hidden rounded-3xl shadow-soft">
              <img src={HERO} alt="Salón del restaurante PLAZA con vista" className="aspect-[4/3] w-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-ink/40 to-transparent" />
            </div>
            <div>
              <p className="eyebrow mb-3">Gastronomía</p>
              {/* Nombre del restaurante desde el perfil del negocio (F3.3). */}
              <h2 className="font-display text-4xl font-600 leading-tight text-ink md:text-5xl">
                {rName2
                  ? (<>{rName1}<br /><span className="italic text-timber-600">{rName2}</span></>)
                  : rName1}
              </h2>
              <p className="mt-5 text-slatey">
                Cocina patagónica de autor con ingredientes frescos de la región: trucha de Alicurá,
                ojo de bife, cervezas artesanales de la Patagonia y nuestros postres caseros. Un espacio
                cálido para disfrutar en familia, con vista y la calidez de nuestra hospitalidad.
              </p>
              <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slatey">
                <span className="inline-flex items-center gap-1.5"><Clock size={15} className="text-timber-500" /> Desayuno 7–11</span>
                <span className="inline-flex items-center gap-1.5"><Clock size={15} className="text-timber-500" /> Almuerzo 12–16</span>
                <span className="inline-flex items-center gap-1.5"><Clock size={15} className="text-timber-500" /> Merienda 16–19</span>
                <span className="inline-flex items-center gap-1.5"><Clock size={15} className="text-timber-500" /> Cena 19–23</span>
              </div>
              <a href="#pedido" className="btn-primary mt-7">
                <UtensilsCrossed size={16} /> Ver carta y pedir
              </a>
            </div>
          </div>
        </Reveal>

        {/* Carta por categorías */}
        {menu.length > 0 && (
          <div className="mt-14">
            <div className="mb-6 flex flex-wrap justify-center gap-2">
              {cats.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setCat(c.id)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                    cat === c.id ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-stone-100'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <RevealGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((m) => (
                <RevealItem key={m.id} as="article" className="flex overflow-hidden rounded-2xl bg-white shadow-card">
                  <img src={m.image_url} alt={m.name} loading="lazy" className="h-auto w-28 shrink-0 object-cover" />
                  <div className="flex flex-1 flex-col p-3.5">
                    <p className="text-sm font-600 leading-tight text-ink">{m.name}</p>
                    {m.description && <p className="mt-0.5 line-clamp-2 text-xs text-slatey">{m.description}</p>}
                    <div className="mt-1 flex flex-wrap gap-1">{(m.tags || []).map((t) => <Tag key={t} tag={t} />)}</div>
                    <span className="mt-auto pt-2 text-sm font-700 tabular-nums text-hilton-700">{formatUSD(m.price_usd)}</span>
                  </div>
                </RevealItem>
              ))}
            </RevealGroup>
            <div className="mt-8 text-center">
              <a href="#pedido" className="inline-flex items-center gap-1.5 text-sm font-medium text-hilton-600 hover:text-hilton-700">
                Ver la carta completa y pedir <ArrowRight size={15} />
              </a>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
