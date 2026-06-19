import { motion, useReducedMotion } from 'framer-motion'

/**
 * Reveal — primitiva de entrada al hacer scroll.
 *
 * Fade + slide-up suave cuando el elemento entra en viewport (una sola vez).
 * Respeta prefers-reduced-motion (no anima si el usuario lo pidió).
 *
 * Props:
 *   - as: etiqueta/elemento a renderizar (default "div")
 *   - delay: retardo en segundos (para escalonar)
 *   - y: desplazamiento inicial en px (default 24)
 *   - once: animar solo la primera vez (default true)
 */
export default function Reveal({
  children,
  as = 'div',
  delay = 0,
  y = 24,
  once = true,
  className = '',
  ...rest
}) {
  const reduce = useReducedMotion()
  const MotionTag = motion[as] || motion.div

  if (reduce) {
    const Tag = as
    return (
      <Tag className={className} {...rest}>
        {children}
      </Tag>
    )
  }

  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: '-10% 0px -10% 0px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}

/**
 * RevealGroup / RevealItem — para escalonar (stagger) una lista de hijos.
 * Envolver el contenedor en <RevealGroup> y cada hijo en <RevealItem>.
 */
export function RevealGroup({ children, className = '', stagger = 0.1, once = true, ...rest }) {
  const reduce = useReducedMotion()
  if (reduce) {
    return <div className={className} {...rest}>{children}</div>
  }
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once, margin: '-8% 0px -8% 0px' }}
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: stagger } },
      }}
      {...rest}
    >
      {children}
    </motion.div>
  )
}

export function RevealItem({ children, as = 'div', y = 24, className = '', ...rest }) {
  const reduce = useReducedMotion()
  const MotionTag = motion[as] || motion.div
  if (reduce) {
    const Tag = as
    return <Tag className={className} {...rest}>{children}</Tag>
  }
  return (
    <MotionTag
      className={className}
      variants={{
        hidden: { opacity: 0, y },
        show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
      }}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}
