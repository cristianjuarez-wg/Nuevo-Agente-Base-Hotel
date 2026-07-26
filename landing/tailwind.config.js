/** @type {import('tailwindcss').Config} */
// Los colores de la instancia viven en theme.config.js (un solo archivo por cliente).
import { brand, accents, neutrals } from './theme.config.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Color de marca de la instancia (theme.config.js). Los componentes usan `brand-*`;
        // cambiar de cliente = cambiar esos valores, sin tocar ningún componente.
        brand,
        ...accents,
        ...neutrals,
      },
      fontFamily: {
        // display: titulares editoriales grandes (serif fino, alto contraste)
        display: ['"Cormorant Garamond"', '"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
        serif: ['"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      letterSpacing: {
        'eyebrow': '0.22em',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
        'card-lg': '0 12px 30px -8px rgb(0 47 90 / 0.18), 0 4px 10px -4px rgb(0 0 0 / 0.08)',
        // sombra editorial cálida y difusa (look premium, menos "tech")
        soft: '0 18px 50px -16px rgb(46 36 22 / 0.22), 0 6px 16px -8px rgb(0 0 0 / 0.06)',
        widget: '0 16px 40px -8px rgb(0 47 90 / 0.30)',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.25rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.45s ease-out both',
        'slide-up-widget': 'slideUpWidget 0.28s ease-out',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
        // zoom lento de imágenes de fondo (efecto "Ken Burns" sutil, hero/galería)
        'slow-zoom': 'slowZoom 18s ease-out forwards',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideUpWidget: {
          from: { opacity: '0', transform: 'translateY(16px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        slowZoom: {
          from: { transform: 'scale(1.08)' },
          to: { transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
