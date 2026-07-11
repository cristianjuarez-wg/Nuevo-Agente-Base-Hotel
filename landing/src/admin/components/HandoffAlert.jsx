import { useEffect, useRef, useState } from 'react'
import { Hand, X } from 'lucide-react'
import { listConversations } from '../../services/api'

// Aviso flotante verde (Fase 4b): cuando una conversación queda marcada por Aura como "requiere
// atención humana", aparece un modal verde en pantalla. Click → va a la bandeja de Conversaciones
// (donde la conversación está distinguida); la ✕ lo cierra. No es una campana con panel: es un
// aviso puntual y descartable. Poll liviano cada 20s.
const POLL_MS = 20000

export default function HandoffAlert() {
  const [pending, setPending] = useState([])   // [{session_id, display_name}]
  const dismissed = useRef(new Set())           // session_ids que el operador ya cerró

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const rows = await listConversations('all')
        if (!alive) return
        const need = rows.filter((r) => r.needs_human?.active && !r.takeover?.active)
        setPending(need
          .filter((r) => !dismissed.current.has(r.session_id))
          .map((r) => ({ session_id: r.session_id, name: r.display_name || r.name || r.phone || 'Un huésped' })))
      } catch { /* silencioso: es un aviso, no crítico */ }
    }
    tick()
    const id = setInterval(tick, POLL_MS)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (!pending.length) return null

  const goToInbox = () => { window.location.hash = 'admin/conversaciones' }
  const close = (sid) => {
    dismissed.current.add(sid)
    setPending((p) => p.filter((x) => x.session_id !== sid))
  }

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-2">
      {pending.slice(0, 3).map((c) => (
        <div key={c.session_id}
          className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-card-lg animate-slide-up">
          <button onClick={goToInbox} className="flex items-start gap-3 text-left">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white">
              <Hand size={16} />
            </span>
            <span>
              <span className="block text-sm font-600 text-emerald-800">Una conversación necesita atención</span>
              <span className="block text-xs text-emerald-700">{c.name} · tocá para tomar la conversación</span>
            </span>
          </button>
          <button onClick={() => close(c.session_id)} aria-label="Cerrar"
            className="rounded-lg p-1 text-emerald-600 hover:bg-emerald-100">
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
