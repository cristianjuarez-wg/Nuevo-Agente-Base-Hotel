import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, MessageSquare, UserCheck } from 'lucide-react'
import { getConversation } from '../../services/api'
import { formatDateTime } from '../ui'

// Burbuja de un mensaje. Mismo lenguaje visual que el chat público (ChatWidget): el huésped
// a la derecha en azul hilton; Aura a la izquierda en linen, con markdown. Una respuesta de
// un OPERADOR humano (sent_by_human) se distingue de Aura con etiqueta y color propio.
function Bubble({ role, content, at, human }) {
  const isUser = role === 'user'
  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      {human && (
        <span className="mb-0.5 inline-flex items-center gap-1 px-1 text-[10px] font-medium text-forest-700">
          <UserCheck size={11} /> Operador
        </span>
      )}
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
          isUser ? 'rounded-br-md bg-hilton-700 text-white'
          : human ? 'rounded-bl-md border border-forest-200 bg-forest-50 text-ink'
          : 'rounded-bl-md bg-linen text-ink'
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      {at && <span className="mt-0.5 px-1 text-[10px] tabular-nums text-slatey">{at}</span>}
    </div>
  )
}

// Transcripción de la charla con Aura que originó un ticket o un lead.
// Reutilizable: recibe el session_id y carga los mensajes del endpoint de conversaciones.
// `pollMs` (opcional): si se pasa, re-consulta los mensajes cada pollMs ms (bandeja en vivo).
// Sin pollMs, carga una sola vez (uso en tickets/leads, sin cambios).
export default function ChatTranscript({ sessionId, pollMs = 0 }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!sessionId) {
      setMessages([])
      setLoading(false)
      return
    }
    let active = true
    setLoading(true)
    setError(false)

    const fetchOnce = (showSpinner) => {
      if (showSpinner) setLoading(true)
      return getConversation(sessionId)
        .then((msgs) => { if (active) { setMessages(Array.isArray(msgs) ? msgs : []); setError(false) } })
        .catch(() => { if (active && showSpinner) setError(true) })  // en refresh silencioso, no rompemos la vista
        .finally(() => { if (active && showSpinner) setLoading(false) })
    }

    fetchOnce(true)
    if (!pollMs) return () => { active = false }

    const id = setInterval(() => fetchOnce(false), pollMs)  // refrescos silenciosos
    return () => { active = false; clearInterval(id) }
  }, [sessionId, pollMs])

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-slatey">
        <Loader2 size={16} className="animate-spin" /> Cargando conversación…
      </div>
    )
  }

  if (error) {
    return <p className="px-4 py-6 text-center text-sm text-slatey">No se pudo cargar la conversación.</p>
  }

  if (!sessionId || messages.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-8 text-center text-slatey">
        <MessageSquare size={22} className="opacity-50" />
        <p className="text-sm">
          {sessionId
            ? 'Esta conversación no tiene mensajes registrados.'
            : 'No se generó desde una conversación de chat.'}
        </p>
      </div>
    )
  }

  // El contenedor padre (un drawer con su propio overflow) gestiona el scroll; acá solo
  // apilamos las burbujas con un ritmo consistente.
  return (
    <div className="space-y-2.5 px-4 py-3">
      {messages.map((m) => (
        <Bubble key={m.id} role={m.role} content={m.content} at={formatDateTime(m.created_at)} human={m.sent_by_human} />
      ))}
    </div>
  )
}
