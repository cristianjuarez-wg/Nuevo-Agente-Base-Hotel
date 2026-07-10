import { Instagram, Phone, Mail, MapPin, LockKeyhole } from 'lucide-react'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

export default function Footer() {
  const HOTEL = useBusinessProfile()
  return (
    <footer className="bg-ink text-white/75">
      <div className="container-wide px-6 py-16 sm:px-10">
        {/* Cierre editorial */}
        <div className="mb-12 max-w-xl">
          <p className="eyebrow-light">{HOTEL.name}</p>
          <p className="mt-4 font-display text-3xl font-500 leading-tight text-white sm:text-4xl">
            {/* F3: copy de instancia — reemplazar por cliente */}
            Te esperamos en {HOTEL.tagline}.
          </p>
          <a href="#reservar" className="btn-primary mt-7 bg-white text-hilton-700 hover:bg-white/90">
            Reservar estadía
          </a>
        </div>

        <div className="grid grid-cols-1 gap-8 border-t border-white/10 pt-10 sm:grid-cols-3">
          <div>
            <p className="font-display text-xl font-600 text-white">{HOTEL.name}</p>
            <p className="mt-1 text-sm text-white/55">{HOTEL.city}</p>
          </div>

          <div className="space-y-3 text-sm">
            <p className="flex items-start gap-2.5">
              <MapPin size={16} strokeWidth={1.6} className="mt-0.5 shrink-0 text-sand-400" />
              {HOTEL.address}
            </p>
            <a href={`tel:${HOTEL.phone}`} className="flex items-center gap-2.5 transition hover:text-white">
              <Phone size={16} strokeWidth={1.6} className="shrink-0 text-sand-400" />
              {HOTEL.phone}
            </a>
            <a href={`mailto:${HOTEL.email}`} className="flex items-center gap-2.5 transition hover:text-white">
              <Mail size={16} strokeWidth={1.6} className="shrink-0 text-sand-400" />
              {HOTEL.email}
            </a>
          </div>

          <div>
            <a
              href={`https://instagram.com/${(HOTEL.instagram || '').replace('@', '')}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-white/25 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-white/10"
              style={{ minHeight: 44 }}
            >
              <Instagram size={18} strokeWidth={1.6} />
              {HOTEL.instagram}
            </a>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-center gap-2 border-t border-white/10 pt-6 text-center text-xs text-white/45 sm:flex-row sm:justify-between">
          <span>© {new Date().getFullYear()} {HOTEL.name} {HOTEL.city} · Demo de presentación.</span>
          <a href="#admin" className="inline-flex items-center gap-1.5 text-white/55 transition hover:text-white">
            <LockKeyhole size={13} strokeWidth={1.6} /> Panel de gestión
          </a>
        </div>
      </div>
    </footer>
  )
}
