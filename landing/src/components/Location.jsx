import { MapPin, Plane, Mountain, Leaf, Phone, Mail, Clock } from 'lucide-react'
import { HOTEL, HIGHLIGHTS } from '../data/hotelInfo'

const ICONS = { MapPin, Plane, Mountain, Leaf }

export default function Location() {
  const mapsSrc = `https://www.google.com/maps?q=${encodeURIComponent(
    HOTEL.mapsQuery
  )}&output=embed`

  return (
    <section id="ubicacion" className="section-pad bg-white">
      <div className="container-x">
        <header className="mx-auto mb-12 max-w-2xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-hilton-500">
            Ubicación
          </p>
          <h2 className="font-serif text-3xl font-700 text-ink sm:text-4xl">
            En el corazón de Bariloche
          </h2>
        </header>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2 lg:items-stretch">
          {/* Mapa */}
          <div className="overflow-hidden rounded-2xl shadow-card-lg">
            <iframe
              title="Ubicación del Hampton by Hilton Bariloche"
              src={mapsSrc}
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              className="h-72 w-full border-0 lg:h-full"
              style={{ minHeight: 288 }}
            />
          </div>

          {/* Info */}
          <div className="flex flex-col justify-center">
            <ul className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {HIGHLIGHTS.map((h) => {
                const Icon = ICONS[h.icon]
                return (
                  <li
                    key={h.label}
                    className="flex items-center gap-3 rounded-xl bg-mist px-4 py-3 text-sm font-medium text-ink"
                  >
                    {Icon && <Icon size={18} className="shrink-0 text-hilton-600" />}
                    {h.label}
                  </li>
                )
              })}
            </ul>

            <div className="space-y-4 rounded-2xl border border-mist p-6">
              <div className="flex items-start gap-3">
                <MapPin size={18} className="mt-0.5 shrink-0 text-hilton-600" />
                <p className="text-sm text-ink">{HOTEL.address}</p>
              </div>
              <div className="flex items-center gap-3">
                <Phone size={18} className="shrink-0 text-hilton-600" />
                <a href={`tel:${HOTEL.phone}`} className="text-sm text-ink hover:text-hilton">
                  {HOTEL.phone}
                </a>
              </div>
              <div className="flex items-center gap-3">
                <Mail size={18} className="shrink-0 text-hilton-600" />
                <a href={`mailto:${HOTEL.email}`} className="text-sm text-ink hover:text-hilton">
                  {HOTEL.email}
                </a>
              </div>
              <div className="flex items-center gap-3 border-t border-mist pt-4">
                <Clock size={18} className="shrink-0 text-hilton-600" />
                <p className="text-sm text-ink">
                  Check-in <span className="font-semibold">{HOTEL.checkIn}</span> · Check-out{' '}
                  <span className="font-semibold">{HOTEL.checkOut}</span>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
