import {
  UtensilsCrossed, Coffee, Wine, Wifi, Car, Snowflake, PawPrint, Award,
} from 'lucide-react'
import { SERVICES } from '../data/hotelInfo'
import { useBusinessProfile } from '../hooks/useBusinessProfile'
import Reveal, { RevealGroup, RevealItem } from './motion/Reveal'

const ICONS = { UtensilsCrossed, Coffee, Wine, Wifi, Car, Snowflake, PawPrint, Award }

export default function Services() {
  const HOTEL = useBusinessProfile()
  return (
    <section id="servicios" className="section-pad bg-white">
      <div className="container-wide px-6 sm:px-10">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="eyebrow">Experiencia</p>
          <h2 className="mt-4 font-display text-4xl font-500 text-ink sm:text-5xl">
            Pensado para tu bienestar
          </h2>
          <div className="rule mt-6" />
          <p className="mt-6 text-base leading-relaxed text-slatey">
            Cada detalle de {HOTEL.name} acompaña tu estadía, desde el desayuno hasta la última
            copa frente al lago.
          </p>
        </Reveal>

        <RevealGroup
          className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl bg-stone-200/60 sm:grid-cols-2 lg:grid-cols-4"
          stagger={0.07}
        >
          {SERVICES.map((s) => {
            const Icon = ICONS[s.icon]
            return (
              <RevealItem
                key={s.title}
                className="group flex flex-col bg-white p-7 transition-colors duration-500 hover:bg-linen"
              >
                <div className="mb-5 text-timber-400 transition-transform duration-500 group-hover:-translate-y-0.5">
                  {Icon && <Icon size={26} strokeWidth={1.5} />}
                </div>
                <h3 className="font-display text-xl font-600 leading-snug text-ink">
                  {s.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slatey">{s.desc}</p>
              </RevealItem>
            )
          })}
        </RevealGroup>
      </div>
    </section>
  )
}
