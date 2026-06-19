import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Send, Sparkles } from 'lucide-react'
import { getGreeting, sendMessage } from '../services/api'

// Session persistente por navegador (sobrevive recargas durante la demo).
function getSessionId() {
  const KEY = 'hampton_chat_session'
  let id = localStorage.getItem(KEY)
  if (!id) {
    id = 'web-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem(KEY, id)
  }
  return id
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-hilton-400 animate-pulse-dot"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </div>
  )
}

function Bubble({ role, children }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[82%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-sm bg-hilton-600 text-white'
            : 'rounded-bl-sm bg-mist text-ink'
        }`}
      >
        {isUser ? (
          children
        ) : (
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [starters, setStarters] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [greeted, setGreeted] = useState(false)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  const sessionId = useRef(getSessionId())

  // Cargar saludo la primera vez que se abre
  useEffect(() => {
    if (open && !greeted) {
      setGreeted(true)
      getGreeting()
        .then((data) => {
          setMessages([{ role: 'assistant', content: data.greeting }])
          setStarters(data.conversation_starters?.slice(0, 4) || [])
        })
        .catch(() =>
          setMessages([
            {
              role: 'assistant',
              content:
                '¡Hola! Soy Aura, la concierge virtual del Hampton by Hilton Bariloche. ¿En qué puedo ayudarte?',
            },
          ])
        )
    }
  }, [open, greeted])

  // Autoscroll al último mensaje
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  const send = useCallback(
    async (text) => {
      const msg = (text ?? input).trim()
      if (!msg || busy) return
      setStarters([])
      setInput('')
      setMessages((m) => [...m, { role: 'user', content: msg }])
      setBusy(true)
      try {
        const data = await sendMessage({ message: msg, sessionId: sessionId.current })
        setMessages((m) => [...m, { role: 'assistant', content: data.response || '…' }])
      } catch {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            content:
              'Disculpá, tuve un problema para responder. ¿Podés intentarlo de nuevo en un momento?',
          },
        ])
      } finally {
        setBusy(false)
        inputRef.current?.focus()
      }
    },
    [input, busy]
  )

  return (
    <>
      {/* Botón flotante (FAB) */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Abrir chat con la concierge virtual"
          className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-hilton-600 text-white shadow-widget transition hover:bg-hilton-700 active:scale-95 sm:bottom-6 sm:right-6"
        >
          <MessageCircle size={26} />
          <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sand-400 opacity-75" />
            <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-sand-500" />
          </span>
        </button>
      )}

      {/* Panel de chat */}
      {open && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white animate-slide-up-widget sm:inset-auto sm:bottom-6 sm:right-6 sm:h-[600px] sm:max-h-[85vh] sm:w-[400px] sm:rounded-2xl sm:shadow-widget">
          {/* Header */}
          <div className="flex items-center justify-between rounded-t-none bg-gradient-to-r from-hilton-700 to-hilton-500 px-4 py-3.5 text-white sm:rounded-t-2xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/15">
                <Sparkles size={20} />
              </div>
              <div className="leading-tight">
                <p className="font-serif text-base font-600">Aura</p>
                <p className="flex items-center gap-1.5 text-xs text-white/80">
                  <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
                  Concierge virtual · en línea
                </p>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Cerrar chat"
              className="flex h-10 w-10 items-center justify-center rounded-lg transition hover:bg-white/10"
            >
              <X size={22} />
            </button>
          </div>

          {/* Mensajes */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-white px-4 py-4">
            {messages.map((m, i) => (
              <Bubble key={i} role={m.role}>
                {m.content}
              </Bubble>
            ))}

            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-mist px-3 py-2">
                  <TypingDots />
                </div>
              </div>
            )}

            {/* Starters sugeridos */}
            {starters.length > 0 && !busy && (
              <div className="flex flex-col gap-2 pt-1">
                {starters.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="self-start rounded-full border border-hilton-200 bg-hilton-50 px-3.5 py-2 text-left text-xs font-medium text-hilton-700 transition hover:bg-hilton-100"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
            className="flex items-center gap-2 border-t border-mist bg-white px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribí tu mensaje…"
              className="flex-1 rounded-full border border-mist bg-mist px-4 py-2.5 text-sm text-ink placeholder:text-slatey focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
            <button
              type="submit"
              disabled={!input.trim() || busy}
              aria-label="Enviar mensaje"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-hilton-600 text-white transition hover:bg-hilton-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send size={18} />
            </button>
          </form>
        </div>
      )}
    </>
  )
}
