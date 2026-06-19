import {
  UtensilsCrossed, Coffee, Wine, Wifi, Car, Snowflake, PawPrint, Award,
} from 'lucide-react'
import { SERVICES } from '../data/hotelInfo'

const ICONS = { UtensilsCrossed, Coffee, Wine, Wifi, Car, Snowflake, PawPrint, Award }

export default function Services() {
  return (
    <section id="servicios" className="section-pad bg-white">
      <div className="container-x">
        <header className="mx-auto mb-12 max-w-2xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-hilton-500">
            Servicios e instalaciones
          </p>
          <h2 className="font-serif text-3xl font-700 text-ink sm:text-4xl">
            Todo lo que necesitás para una estadía perfecta
          </h2>
        </header>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {SERVICES.map((s) => {
            const Icon = ICONS[s.icon]
            return (
              <div
                key={s.title}
                className="rounded-2xl border border-mist bg-white p-6 shadow-card transition hover:border-hilton-100 hover:shadow-card-lg"
              >
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-hilton-50 text-hilton-600">
                  {Icon && <Icon size={22} />}
                </div>
                <h3 className="mb-1.5 font-serif text-lg font-600 text-ink">
                  {s.title}
                </h3>
                <p className="text-sm leading-relaxed text-slatey">{s.desc}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
