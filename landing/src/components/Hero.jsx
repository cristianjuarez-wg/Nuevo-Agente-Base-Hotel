import { useRef } from 'react'
import { motion, useScroll, useTransform, useReducedMotion } from 'framer-motion'
import { ArrowUpRight } from 'lucide-react'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

// Imagen hero: vista aérea del lago Nahuel Huapi al atardecer (foto oficial del hotel).
const HERO_IMG = '/fotos/hero-lago-atardecer.jpg'

const ease = [0.22, 1, 0.36, 1]

export default function Hero() {
  const HOTEL = useBusinessProfile()
  const ref = useRef(null)
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start start', 'end start'],
  })
  // Parallax sutil: la imagen se mueve más lento que el scroll.
  const imgY = useTransform(scrollYProgress, [0, 1], ['0%', reduce ? '0%' : '18%'])
  const overlayOpacity = useTransform(scrollYProgress, [0, 1], [1, 0.4])

  return (
    <section
      id="inicio"
      ref={ref}
      className="relative flex min-h-dvh items-center overflow-hidden"
    >
      {/* Imagen de fondo con parallax + zoom lento */}
      <motion.div className="absolute inset-0" style={{ y: imgY }}>
        <img
          src={HERO_IMG}
          alt={`Vista del hotel ${HOTEL.name} ${HOTEL.city}`}
          className="h-[118%] w-full object-cover animate-slow-zoom"
          fetchpriority="high"
        />
      </motion.div>

      {/* Overlay editorial: oscurece más abajo a la izquierda para asentar el texto */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-tr from-ink/85 via-ink/45 to-ink/20"
        style={{ opacity: overlayOpacity }}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-ink/60 via-transparent to-transparent" />

      {/* Contenido — alineado a la izquierda, editorial */}
      <div className="container-wide relative z-10 px-6 sm:px-10">
        <div className="max-w-2xl">
          <motion.p
            className="eyebrow-light"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease }}
          >
            {HOTEL.tagline}
          </motion.p>

          <h1 className="mt-6 font-display text-5xl font-500 leading-[1.05] text-white sm:text-6xl md:text-7xl lg:text-8xl">
            <motion.span
              className="block"
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.08, ease }}
            >
              Un refugio
            </motion.span>
            <motion.span
              className="block italic text-sand-100"
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.18, ease }}
            >
              en la Patagonia
            </motion.span>
          </h1>

          <motion.p
            className="mt-7 max-w-lg text-base leading-relaxed text-white/85 sm:text-lg"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease }}
          >
            {/* F3: copy de instancia — reemplazar por cliente (geografía específica) */}
            {HOTEL.tagline}. Confort y hospitalidad en el corazón de {HOTEL.city}.
          </motion.p>

          <motion.div
            className="mt-10 flex flex-col gap-3 sm:flex-row"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.42, ease }}
          >
            <a href="#reservar" className="btn-primary">
              Reservar estadía
            </a>
            <a href="#habitaciones" className="btn-ghost-light">
              Explorar el hotel
            </a>
            {/* Acceso sutil a la presentación (Wigou × Hampton). Sin recuadro: pasa algo
                desapercibido entre los dos CTA, pero invita a quien tenga curiosidad. */}
            <a
              href="/presentacion/hampton-wigou.html"
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center justify-center gap-1.5 px-2 py-3 text-sm font-medium tracking-wide text-white/70 underline-offset-4 transition hover:text-white hover:underline"
              style={{ minHeight: 44 }}
            >
              Ver presentación
              <ArrowUpRight size={15} className="transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </a>
          </motion.div>
        </div>
      </div>

      {/* Marca de scroll editorial */}
      <div className="absolute bottom-8 left-1/2 z-10 -translate-x-1/2 sm:left-auto sm:right-10 sm:translate-x-0">
        <a
          href="#habitaciones"
          aria-label="Descubrir más"
          className="group flex flex-col items-center gap-2 text-white/60 transition hover:text-white"
        >
          <span className="text-[10px] uppercase tracking-eyebrow">Descubrir</span>
          <span className="h-12 w-px overflow-hidden bg-white/30">
            <span className="block h-1/2 w-full animate-[slideUp_1.6s_ease-in-out_infinite] bg-white" />
          </span>
        </a>
      </div>
    </section>
  )
}
