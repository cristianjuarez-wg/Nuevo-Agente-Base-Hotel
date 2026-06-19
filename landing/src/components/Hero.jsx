import { ChevronDown, Star } from 'lucide-react'
import { HOTEL } from '../data/hotelInfo'

// Imagen hero real del hotel (CDN del sitio oficial).
const HERO_IMG =
  'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_30-1920w.jpg'

export default function Hero() {
  return (
    <section
      id="inicio"
      className="relative flex min-h-dvh items-center justify-center overflow-hidden"
    >
      {/* Imagen de fondo */}
      <div className="absolute inset-0">
        <img
          src={HERO_IMG}
          alt="Habitación del Hampton by Hilton Bariloche con vista a la Patagonia"
          className="h-full w-full object-cover"
          fetchpriority="high"
        />
        {/* Overlay para legibilidad del texto */}
        <div className="absolute inset-0 bg-gradient-to-b from-ink/70 via-ink/45 to-ink/75" />
      </div>

      {/* Contenido */}
      <div className="container-x relative z-10 px-5 text-center sm:px-8">
        <div className="mx-auto flex max-w-2xl flex-col items-center animate-slide-up">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-4 py-1.5 text-xs font-medium uppercase tracking-wider text-white backdrop-blur">
            <Star size={13} className="fill-sand text-sand" />
            {HOTEL.tagline}
          </span>

          <h1 className="font-serif text-4xl font-700 leading-tight text-white sm:text-5xl md:text-6xl">
            Hampton by Hilton
            <span className="mt-1 block text-2xl font-500 text-white/90 sm:text-3xl">
              Bariloche
            </span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-white/85 sm:text-lg">
            Confort, calidez y hospitalidad en el corazón de la Patagonia. A solo
            150 metros del Centro Cívico, con desayuno buffet incluido.
          </p>

          <div className="mt-8 flex w-full flex-col items-center gap-3 sm:w-auto sm:flex-row">
            <a href="#reservar" className="btn-primary w-full sm:w-auto">
              Consultar disponibilidad
            </a>
            <a
              href="#habitaciones"
              className="w-full rounded-xl border border-white/40 bg-white/5 px-6 py-3 text-sm font-semibold text-white backdrop-blur transition hover:bg-white/15 active:scale-[0.98] sm:w-auto"
              style={{ minHeight: 44 }}
            >
              Ver habitaciones
            </a>
          </div>
        </div>
      </div>

      {/* Indicador de scroll */}
      <a
        href="#habitaciones"
        aria-label="Ver más"
        className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2 text-white/70 transition hover:text-white"
      >
        <ChevronDown size={28} className="animate-bounce" />
      </a>
    </section>
  )
}
