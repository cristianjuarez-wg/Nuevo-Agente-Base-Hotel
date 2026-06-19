import { useState, useEffect } from 'react'
import { Menu, X } from 'lucide-react'

const LINKS = [
  { href: '#habitaciones', label: 'Habitaciones' },
  { href: '#reservar', label: 'Reservar' },
  { href: '#servicios', label: 'Servicios' },
  { href: '#galeria', label: 'Galería' },
  { href: '#ubicacion', label: 'Ubicación' },
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Bloquear scroll del body cuando el menú móvil está abierto
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  const close = () => setOpen(false)

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-colors duration-300 ${
        scrolled || open
          ? 'bg-white/95 shadow-card backdrop-blur'
          : 'bg-transparent'
      }`}
    >
      <nav className="container-x flex items-center justify-between px-5 py-3 sm:px-8">
        {/* Logo / marca */}
        <a href="#inicio" onClick={close} className="flex flex-col leading-tight">
          <span
            className={`font-serif text-lg font-700 transition-colors ${
              scrolled || open ? 'text-hilton-700' : 'text-white'
            }`}
          >
            Hampton <span className="font-sans text-xs font-medium align-top">by Hilton</span>
          </span>
          <span
            className={`text-[11px] font-medium uppercase tracking-wider transition-colors ${
              scrolled || open ? 'text-slatey' : 'text-white/80'
            }`}
          >
            Bariloche
          </span>
        </a>

        {/* Links desktop */}
        <ul className="hidden items-center gap-7 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className={`text-sm font-medium transition-colors hover:text-hilton ${
                  scrolled ? 'text-ink' : 'text-white/90'
                }`}
              >
                {l.label}
              </a>
            </li>
          ))}
          <li>
            <a href="#reservar" className="btn-primary px-5 py-2.5 text-sm">
              Reservar ahora
            </a>
          </li>
        </ul>

        {/* Botón menú móvil — touch target 44px */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={open}
          className={`flex h-11 w-11 items-center justify-center rounded-lg transition-colors md:hidden ${
            scrolled || open ? 'text-hilton-700 hover:bg-hilton-50' : 'text-white hover:bg-white/10'
          }`}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </nav>

      {/* Menú móvil desplegable */}
      {open && (
        <div className="border-t border-hilton-100 bg-white md:hidden">
          <ul className="container-x flex flex-col px-5 py-2">
            {LINKS.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  onClick={close}
                  className="block rounded-lg px-2 py-3.5 text-base font-medium text-ink hover:bg-hilton-50 hover:text-hilton"
                >
                  {l.label}
                </a>
              </li>
            ))}
            <li className="py-2">
              <a href="#reservar" onClick={close} className="btn-primary w-full">
                Reservar ahora
              </a>
            </li>
          </ul>
        </div>
      )}
    </header>
  )
}
