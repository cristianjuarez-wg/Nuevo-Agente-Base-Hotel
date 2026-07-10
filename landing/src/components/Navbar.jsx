import { useState, useEffect } from 'react'
import { Menu, X, LockKeyhole } from 'lucide-react'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

const LINKS = [
  { href: '#habitaciones', label: 'Habitaciones' },
  { href: '#reservar', label: 'Reservar' },
  { href: '#servicios', label: 'Servicios' },
  { href: '#restaurante', label: 'Restaurante' },
  { href: '#galeria', label: 'Galería' },
  { href: '#ubicacion', label: 'Ubicación' },
]

export default function Navbar() {
  const HOTEL = useBusinessProfile()
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  const solid = scrolled || open
  const close = () => setOpen(false)

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-all duration-500 ${
        solid ? 'bg-linen/95 shadow-[0_1px_0_0_rgb(0_0_0/0.06)] backdrop-blur' : 'bg-transparent'
      }`}
    >
      <nav className="container-wide flex items-center justify-between px-6 py-4 sm:px-10">
        {/* Logo / marca */}
        <a href="#inicio" onClick={close} className="flex flex-col leading-none">
          <span
            className={`font-display text-2xl font-600 tracking-wide transition-colors ${
              solid ? 'text-hilton-700' : 'text-white'
            }`}
          >
            {HOTEL.name}
          </span>
          <span
            className={`mt-0.5 text-[10px] font-medium uppercase tracking-eyebrow transition-colors ${
              solid ? 'text-timber-500' : 'text-white/75'
            }`}
          >
            {HOTEL.regionLine}
          </span>
        </a>

        {/* Links desktop */}
        <ul className="hidden items-center gap-9 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className={`text-[13px] font-medium tracking-wide transition-colors hover:text-hilton ${
                  solid ? 'text-ink/80' : 'text-white/90'
                }`}
              >
                {l.label}
              </a>
            </li>
          ))}
          <li>
            <a
              href="#reservar"
              className={`rounded-full border px-5 py-2 text-[13px] font-medium tracking-wide transition ${
                solid
                  ? 'border-hilton bg-hilton text-white hover:bg-hilton-700'
                  : 'border-white/50 text-white hover:bg-white/10'
              }`}
            >
              Reservar
            </a>
          </li>
          {/* Acceso interno al panel de gestión (separado de los links de huésped). */}
          <li>
            <a
              href="#admin"
              title="Acceso al panel de gestión (interno)"
              className={`inline-flex items-center gap-1.5 text-[13px] font-medium tracking-wide transition-colors hover:text-hilton ${
                solid ? 'text-ink/55' : 'text-white/70'
              }`}
            >
              <LockKeyhole size={14} strokeWidth={1.7} /> Panel de gestión
            </a>
          </li>
        </ul>

        {/* Botón menú móvil */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={open}
          className={`flex h-11 w-11 items-center justify-center rounded-full transition-colors md:hidden ${
            solid ? 'text-hilton-700 hover:bg-ink/[0.05]' : 'text-white hover:bg-white/10'
          }`}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Menú móvil */}
      {open && (
        <div className="border-t border-ink/10 bg-linen md:hidden">
          <ul className="container-wide flex flex-col px-6 py-3">
            {LINKS.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  onClick={close}
                  className="block border-b border-ink/[0.06] py-4 font-display text-xl text-ink last:border-0 hover:text-hilton"
                >
                  {l.label}
                </a>
              </li>
            ))}
            <li className="pt-4">
              <a href="#reservar" onClick={close} className="btn-primary w-full">
                Reservar estadía
              </a>
            </li>
            {/* Acceso interno al panel de gestión. */}
            <li className="pt-3">
              <a
                href="#admin"
                onClick={close}
                className="flex items-center justify-center gap-2 rounded-xl border border-ink/15 py-3 text-sm font-medium text-ink/70 transition hover:bg-ink/[0.04]"
              >
                <LockKeyhole size={15} strokeWidth={1.7} /> Panel de gestión
              </a>
            </li>
          </ul>
        </div>
      )}
    </header>
  )
}
