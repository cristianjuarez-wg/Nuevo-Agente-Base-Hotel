import { useState } from 'react'
import { LockKeyhole, X, Loader2 } from 'lucide-react'
import { setAdminKey } from '../../services/api'

/**
 * Modal que pide la clave de administración para acciones críticas.
 *
 * Props:
 *   - onConfirm(): se llama tras guardar la clave (el caller reintenta su acción).
 *   - onClose(): cierra sin hacer nada.
 *   - error: mensaje opcional (ej. "Clave incorrecta") cuando se reabre tras un 403.
 */
export default function AdminKeyModal({ onConfirm, onClose, error }) {
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!key.trim()) return
    setBusy(true)
    setAdminKey(key.trim())
    // El caller reintenta la acción; si la clave es incorrecta, el backend responde 403
    // y el caller vuelve a abrir este modal con el error.
    await onConfirm()
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600">
              <LockKeyhole size={18} />
            </div>
            <h3 className="font-serif text-lg font-700 text-ink">Acción protegida</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </div>
        <p className="mb-4 text-sm text-slatey">
          Esta acción modifica configuración sensible. Ingresá la clave de administración para continuar.
        </p>
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          placeholder="Clave de administración"
          autoFocus
          className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
        />
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <div className="mt-5 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">
            Cancelar
          </button>
          <button
            onClick={submit}
            disabled={busy || !key.trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-hilton-700 disabled:opacity-50"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <LockKeyhole size={15} />} Continuar
          </button>
        </div>
      </div>
    </div>
  )
}
