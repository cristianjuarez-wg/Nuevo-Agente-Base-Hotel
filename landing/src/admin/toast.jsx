import { useEffect, useState } from 'react'
import { CheckCircle2, AlertTriangle, X } from 'lucide-react'

// Toast global ligero, sin dependencias ni Context: un store con suscriptores.
// Uso: import { toast } from '../toast'  →  toast.success('Guardado'), toast.error('...')
let _id = 0
const _listeners = new Set()
let _toasts = []

function _emit() {
  for (const fn of _listeners) fn(_toasts)
}

function _push(message, tone) {
  const id = ++_id
  _toasts = [..._toasts, { id, message, tone }]
  _emit()
  // Auto-dismiss a los 3.5s (best practice de toasts).
  setTimeout(() => _dismiss(id), 3500)
}

function _dismiss(id) {
  _toasts = _toasts.filter((t) => t.id !== id)
  _emit()
}

export const toast = {
  success: (message) => _push(message, 'success'),
  error: (message) => _push(message, 'error'),
  info: (message) => _push(message, 'info'),
}

// Montar UNA vez en el layout del admin. Renderiza los toasts apilados abajo-derecha.
export function Toaster() {
  const [items, setItems] = useState(_toasts)
  useEffect(() => {
    _listeners.add(setItems)
    return () => _listeners.delete(setItems)
  }, [])

  if (items.length === 0) return null

  const tones = {
    success: { bg: 'bg-green-600', Icon: CheckCircle2 },
    error: { bg: 'bg-red-600', Icon: AlertTriangle },
    info: { bg: 'bg-hilton-700', Icon: CheckCircle2 },
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2" aria-live="polite">
      {items.map((t) => {
        const { bg, Icon } = tones[t.tone] || tones.info
        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-center gap-2.5 rounded-xl ${bg} px-4 py-3 text-sm font-medium text-white shadow-card-lg animate-slide-up`}
          >
            <Icon size={16} className="shrink-0" />
            <span className="max-w-xs">{t.message}</span>
            <button onClick={() => _dismiss(t.id)} aria-label="Cerrar" className="ml-1 text-white/70 hover:text-white">
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
