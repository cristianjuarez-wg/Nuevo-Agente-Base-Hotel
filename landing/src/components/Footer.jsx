import { Instagram, Phone, Mail, MapPin } from 'lucide-react'
import { HOTEL } from '../data/hotelInfo'

export default function Footer() {
  return (
    <footer className="bg-ink text-white/80">
      <div className="container-x px-5 py-12 sm:px-8">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
          <div>
            <p className="font-serif text-xl font-700 text-white">
              Hampton <span className="font-sans text-sm font-medium">by Hilton</span>
            </p>
            <p className="mt-1 text-sm text-white/60">{HOTEL.tagline}</p>
          </div>

          <div className="space-y-3 text-sm">
            <p className="flex items-start gap-2">
              <MapPin size={16} className="mt-0.5 shrink-0 text-sand-400" />
              {HOTEL.address}
            </p>
            <a href={`tel:${HOTEL.phone}`} className="flex items-center gap-2 hover:text-white">
              <Phone size={16} className="shrink-0 text-sand-400" />
              {HOTEL.phone}
            </a>
            <a href={`mailto:${HOTEL.email}`} className="flex items-center gap-2 hover:text-white">
              <Mail size={16} className="shrink-0 text-sand-400" />
              {HOTEL.email}
            </a>
          </div>

          <div>
            <a
              href="https://instagram.com/hamptonbariloche"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-white/20 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-white/10"
              style={{ minHeight: 44 }}
            >
              <Instagram size={18} />
              {HOTEL.instagram}
            </a>
          </div>
        </div>

        <div className="mt-10 border-t border-white/10 pt-6 text-center text-xs text-white/50">
          © {new Date().getFullYear()} Hampton by Hilton Bariloche · Demo de presentación.
        </div>
      </div>
    </footer>
  )
}
