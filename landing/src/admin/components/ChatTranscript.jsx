import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Loader2, MessageSquare } from 'lucide-react'
import { getConversation } from '../../services/api'
import { formatDateTime } from '../ui'

// Burbuja de un mensaje. Mismo lenguaje visual que el chat público (ChatWidget): el huésped
// a la derecha en azul hilton; Aura a la izquierda en linen, con markdown.
function Bubble({ role, content, at }) {
  const isUser = role === 'user'
  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
          isUser ? 'rounded-br-md bg-hilton-700 text-white' : 'rounded-bl-md bg-linen text-ink'
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
export default function ChatTranscript({ sessionId }) {
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
    getConversation(sessionId)
      .then((msgs) => { if (active) setMessages(Array.isArray(msgs) ? msgs : []) })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [sessionId])

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
        <Bubble key={m.id} role={m.role} content={m.content} at={formatDateTime(m.created_at)} />
      ))}
    </div>
  )
}
