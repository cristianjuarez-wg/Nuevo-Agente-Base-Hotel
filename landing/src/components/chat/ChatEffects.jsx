import { useMemo } from 'react'

/**
 * Capa decorativa de efectos animados del chat, según el tema estacional.
 * Render puramente CSS (ver index.css → .chat-fx). pointer-events:none, detrás
 * de las burbujas, baja opacidad. Respeta prefers-reduced-motion vía el CSS.
 *
 * Intensidad: "muy sutil" → pocas partículas (10-12), opacidad ~0.4.
 *
 * Props:
 *   effect: "none" | "snow" | "snow_gold" | "leaves" | "bunny"
 */

// Generador determinístico simple (mismas posiciones en cada render del montaje).
function rng(seed) {
  let s = seed
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

// Copos de nieve cayendo.
// `glow` (opcional) agrega un halo sutil para que el copo se note sobre fondos claros.
function FallingParticles({ count, color, sizeRange, seed, opacity, glow }) {
  const items = useMemo(() => {
    const r = rng(seed)
    return Array.from({ length: count }, () => {
      const size = sizeRange[0] + r() * (sizeRange[1] - sizeRange[0])
      return {
        left: `${r() * 100}%`,
        size,
        duration: 7 + r() * 7,          // 7-14s caída lenta
        delay: -r() * 14,               // arranca desfasado (negativo = ya en curso)
        drift: `${(r() - 0.5) * 40}px`, // deriva horizontal leve
        blur: r() > 0.6 ? 0.6 : 0,
      }
    })
  }, [count, seed, sizeRange])

  return items.map((p, i) => (
    <span
      key={i}
      className="fx-fall"
      style={{
        left: p.left,
        width: p.size,
        height: p.size,
        background: color,
        boxShadow: glow ? `0 0 ${p.size * 1.2}px ${glow}` : undefined,
        filter: p.blur ? `blur(${p.blur}px)` : undefined,
        animationDuration: `${p.duration}s`,
        animationDelay: `${p.delay}s`,
        '--fx-drift': p.drift,
        '--fx-opacity': opacity,
      }}
    />
  ))
}

// Destellos dorados que titilan en el lugar (Navidad)
function Twinkles({ count, color, seed, opacity }) {
  const items = useMemo(() => {
    const r = rng(seed)
    return Array.from({ length: count }, () => ({
      left: `${r() * 95}%`,
      top: `${r() * 90}%`,
      size: 2 + r() * 3,
      duration: 2 + r() * 2.5,
      delay: -r() * 4,
    }))
  }, [count, seed])

  return items.map((p, i) => (
    <span
      key={i}
      className="fx-twinkle"
      style={{
        left: p.left,
        top: p.top,
        width: p.size,
        height: p.size,
        background: color,
        boxShadow: `0 0 ${p.size * 1.5}px ${color}`,
        animationDuration: `${p.duration}s`,
        animationDelay: `${p.delay}s`,
        '--fx-opacity': opacity,
      }}
    />
  ))
}

// Hojas/destellos flotando hacia arriba (Verano)
function RisingParticles({ count, color, sizeRange, seed, opacity }) {
  const items = useMemo(() => {
    const r = rng(seed)
    return Array.from({ length: count }, () => {
      const size = sizeRange[0] + r() * (sizeRange[1] - sizeRange[0])
      return {
        left: `${r() * 100}%`,
        size,
        duration: 9 + r() * 8,
        delay: -r() * 17,
        drift: `${(r() - 0.5) * 50}px`,
      }
    })
  }, [count, seed, sizeRange])

  return items.map((p, i) => (
    <span
      key={i}
      className="fx-rise"
      style={{
        left: p.left,
        width: p.size,
        height: p.size,
        background: color,
        animationDuration: `${p.duration}s`,
        animationDelay: `${p.delay}s`,
        '--fx-drift': p.drift,
        '--fx-opacity': opacity,
      }}
    />
  ))
}

export default function ChatEffects({ effect }) {
  if (!effect || effect === 'none') return null

  return (
    <div className="chat-fx" aria-hidden="true">
      {effect === 'snow' && (
        <FallingParticles
          count={12} color="#7fb3e0" glow="#bcdcf5"
          sizeRange={[3, 6]} seed={7} opacity={0.7}
        />
      )}

      {effect === 'snow_gold' && (
        <>
          <FallingParticles
            count={9} color="#cfe2f5" glow="#9cc4ec"
            sizeRange={[3, 6]} seed={7} opacity={0.75}
          />
          <Twinkles count={6} color="#f5d680" seed={42} opacity={0.8} />
        </>
      )}

      {effect === 'leaves' && (
        <RisingParticles count={10} color="#7fd1bd" sizeRange={[3, 6]} seed={19} opacity={0.4} />
      )}

      {effect === 'bunny' && (
        <span className="fx-bunny" style={{ opacity: 0.92 }}>🐰</span>
      )}
    </div>
  )
}
