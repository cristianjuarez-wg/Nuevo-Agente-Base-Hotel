import { MapPin, Plane, Mountain, Leaf, Phone, Mail, Clock } from 'lucide-react'
import { HIGHLIGHTS } from '../data/hotelInfo'
import { useBusinessProfile } from '../hooks/useBusinessProfile'
import Reveal, { RevealGroup, RevealItem } from './motion/Reveal'

const ICONS = { MapPin, Plane, Mountain, Leaf }

export default function Location() {
  const HOTEL = useBusinessProfile()
  const mapsSrc = `https://www.google.com/maps?q=${encodeURIComponent(
    HOTEL.mapsQuery
  )}&output=embed`

  return (
    <section id="ubicacion" className="section-pad bg-linen">
      <div className="container-wide px-6 sm:px-10">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="eyebrow">Ubicación</p>
          <h2 className="mt-4 font-display text-4xl font-500 text-ink sm:text-5xl">
            En el corazón de {HOTEL.city}
          </h2>
          <div className="rule mt-6" />
          {/* F3: copy de instancia — reemplazar por cliente (geografía específica) */}
          <p className="mt-6 text-base leading-relaxed text-slatey">
            A pasos del Centro Cívico y frente al Nahuel Huapi, el punto de partida ideal
            para descubrir la Patagonia.
          </p>
        </Reveal>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-2 lg:items-stretch">
          {/* Mapa */}
          <Reveal className="overflow-hidden rounded-2xl shadow-soft" y={32}>
            <iframe
              title={`Ubicación de ${HOTEL.name}`}
              src={mapsSrc}
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              className="h-80 w-full border-0 lg:h-full"
              style={{ minHeight: 320 }}
            />
          </Reveal>

          {/* Info */}
          <div className="flex flex-col justify-center">
            <RevealGroup className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2" stagger={0.08}>
              {HIGHLIGHTS.map((h) => {
                const Icon = ICONS[h.icon]
                return (
                  <RevealItem
                    key={h.label}
                    className="flex items-center gap-3 rounded-xl bg-white px-4 py-3.5 text-sm font-medium text-ink shadow-card"
                  >
                    {Icon && <Icon size={18} strokeWidth={1.6} className="shrink-0 text-timber-400" />}
                    {h.label}
                  </RevealItem>
                )
              })}
            </RevealGroup>

            <Reveal className="space-y-4 rounded-2xl border border-stone-200 bg-white p-7" delay={0.1}>
              <div className="flex items-start gap-3">
                <MapPin size={18} strokeWidth={1.6} className="mt-0.5 shrink-0 text-hilton-600" />
                <p className="text-sm text-ink">{HOTEL.address}</p>
              </div>
              <div className="flex items-center gap-3">
                <Phone size={18} strokeWidth={1.6} className="shrink-0 text-hilton-600" />
                <a href={`tel:${HOTEL.phone}`} className="text-sm text-ink transition hover:text-hilton">
                  {HOTEL.phone}
                </a>
              </div>
              <div className="flex items-center gap-3">
                <Mail size={18} strokeWidth={1.6} className="shrink-0 text-hilton-600" />
                <a href={`mailto:${HOTEL.email}`} className="text-sm text-ink transition hover:text-hilton">
                  {HOTEL.email}
                </a>
              </div>
              <div className="flex items-center gap-3 border-t border-stone-200 pt-4">
                <Clock size={18} strokeWidth={1.6} className="shrink-0 text-hilton-600" />
                <p className="text-sm text-ink">
                  Check-in <span className="font-semibold">{HOTEL.checkIn}</span> · Check-out{' '}
                  <span className="font-semibold">{HOTEL.checkOut}</span>
                </p>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  )
}
