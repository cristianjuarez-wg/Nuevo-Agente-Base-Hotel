import { useEffect } from 'react'
import { X, Check, Info, MessageCircle } from 'lucide-react'

/**
 * Modal "¿Qué puede hacer Aura?" — encauza las expectativas del visitante: qué SÍ puede hacer
 * el agente, ejemplos de preguntas (clickeables) y qué queda fuera de su alcance.
 * Props:
 *   t       strings i18n del idioma activo (getStrings(lang))
 *   onClose cerrar el modal
 *   onAsk   (texto) => envía esa pregunta al chat (y cierra). Para los ejemplos accionables.
 */
export default function HelpModal({ t, onClose, onAsk }) {
  // Cerrar con Esc.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center p-3" role="dialog" aria-modal="true" aria-label={t.helpTitle}>
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />

      <div className="relative flex max-h-full w-full max-w-sm flex-col overflow-hidden rounded-2xl bg-white shadow-card-lg animate-slide-up">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 border-b border-stone-100 px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-hilton-50 text-hilton-600">
              <Info size={16} />
            </span>
            <h3 className="font-display text-base font-600 text-ink">{t.helpTitle}</h3>
          </div>
          <button onClick={onClose} aria-label={t.close} className="rounded-lg p-1.5 text-slatey transition hover:bg-stone-100">
            <X size={18} />
          </button>
        </div>

        {/* Cuerpo */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <p className="text-sm leading-relaxed text-slatey">{t.helpIntro}</p>

          {/* Capacidades */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slatey">{t.helpCanTitle}</p>
            <ul className="space-y-1.5">
              {t.helpCan.map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-ink">
                  <Check size={15} className="mt-0.5 shrink-0 text-hilton-600" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Ejemplos accionables */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slatey">{t.helpExamplesTitle}</p>
            <div className="flex flex-wrap gap-2">
              {t.helpExamples.map((ex) => (
                <button
                  key={ex}
                  onClick={() => onAsk(ex)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-timber-200 bg-linen px-3 py-1.5 text-left text-xs font-medium text-timber-600 transition hover:border-timber-300 hover:bg-stone-50"
                >
                  <MessageCircle size={12} /> {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Fuera de alcance */}
          <div className="rounded-xl bg-stone-50 p-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slatey">{t.helpOutTitle}</p>
            <p className="text-sm leading-relaxed text-slatey">{t.helpOut}</p>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-stone-100 px-5 py-3">
          <button
            onClick={onClose}
            className="w-full rounded-xl bg-hilton-700 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-800"
          >
            {t.helpClose}
          </button>
        </div>
      </div>
    </div>
  )
}
