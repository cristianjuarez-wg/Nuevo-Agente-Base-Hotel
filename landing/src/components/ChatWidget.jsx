import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Send, Sparkles, RotateCcw, Languages, Check } from 'lucide-react'
import { getGreeting, sendMessage, clearChat, getChatTheme } from '../services/api'
import RoomCard from './chat/RoomCard'
import DatePickerCard from './chat/DatePickerCard'
import ChatEffects from './chat/ChatEffects'
import { LANGUAGES, getStrings, detectInitialLang, persistLang } from '../i18n/chat'

// Convierte los tokens de un tema en un objeto de estilos CSS inline.
// Solo sobreescribe los que vienen definidos en el tema.
function buildThemeStyles(theme) {
  if (!theme) return {}
  return {
    '--chat-header-bg': theme.header_bg || undefined,
    '--chat-header-text': theme.header_text || undefined,
    '--chat-accent': theme.accent_color || undefined,
    '--chat-bubble-bg': theme.bubble_bg || undefined,
    '--chat-fab-bg': theme.fab_bg || undefined,
    '--chat-fab-text': theme.fab_text || undefined,
  }
}

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
          className="h-2 w-2 rounded-full bg-timber-300 animate-pulse-dot"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </div>
  )
}

function Bubble({ role, children, accentColor, bubbleBg }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[82%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'rounded-br-md text-white'
            : 'rounded-bl-md text-ink'
        }${!isUser && !bubbleBg ? ' bg-linen' : ''}${isUser && !accentColor ? ' bg-hilton-700' : ''}`}
        style={isUser && accentColor
          ? { backgroundColor: accentColor }
          : !isUser && bubbleBg
          ? { backgroundColor: bubbleBg }
          : undefined}
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
  const [resetting, setResetting] = useState(false)
  const [theme, setTheme] = useState(null)
  const [lang, setLang] = useState(detectInitialLang)
  const [langMenu, setLangMenu] = useState(false)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  const sessionId = useRef(getSessionId())
  const t = getStrings(lang)

  // Cargar tema visual una sola vez al montar
  useEffect(() => {
    getChatTheme().then(setTheme).catch(() => {})
  }, [])

  const loadGreeting = useCallback((forLang) => {
    const useLang = forLang || lang
    setGreeted(true)
    getGreeting(useLang)
      .then((data) => {
        setMessages([{ role: 'assistant', content: data.greeting }])
        // Los starters vienen del perfil (español); solo se muestran en ES para no mezclar.
        setStarters(useLang === 'es' ? (data.conversation_starters?.slice(0, 4) || []) : [])
      })
      .catch(() =>
        setMessages([{ role: 'assistant', content: getStrings(useLang).greetingFallback }])
      )
  }, [lang])

  // Cambiar idioma: persiste, reinicia el saludo en el nuevo idioma y limpia la sesión
  // en el backend para que Aura siga 100% en el idioma elegido.
  const changeLang = useCallback((code) => {
    if (code === lang) { setLangMenu(false); return }
    setLang(code)
    persistLang(code)
    setLangMenu(false)
    clearChat(sessionId.current).catch(() => {})
    loadGreeting(code)
  }, [lang, loadGreeting])

  // Cargar saludo la primera vez que se abre
  useEffect(() => {
    if (open && !greeted) loadGreeting()
  }, [open, greeted, loadGreeting])

  // Autoscroll al último mensaje
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  // Auto-resize del textarea: crece con el contenido (hasta max-h, luego scrollea).
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  const send = useCallback(
    async (text) => {
      const msg = (text ?? input).trim()
      if (!msg || busy) return
      setStarters([])
      setInput('')
      setMessages((m) => [...m, { role: 'user', content: msg }])
      setBusy(true)
      try {
        const data = await sendMessage({ message: msg, sessionId: sessionId.current, language: lang })
        setMessages((m) => [
          ...m,
          { role: 'assistant', content: data.response || '…', cards: data.cards || [] },
        ])
      } catch {
        setMessages((m) => [
          ...m,
          { role: 'assistant', content: getStrings(lang).errorReply },
        ])
      } finally {
        setBusy(false)
        inputRef.current?.focus()
      }
    },
    [input, busy, lang]
  )

  const resetChat = useCallback(async () => {
    if (busy || resetting) return
    setResetting(true)
    try {
      await clearChat(sessionId.current)
    } catch { /* ignorar error — el frontend se resetea igual */ }
    const KEY = 'hampton_chat_session'
    const newId = 'web-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem(KEY, newId)
    sessionId.current = newId
    setMessages([])
    setStarters([])
    setInput('')
    setResetting(false)
    loadGreeting()
  }, [busy, resetting, loadGreeting])

  // Acción de una tarjeta: 'send_message' inyecta un mensaje al chat; 'open_url' abre link.
  const handleCardAction = useCallback(
    (action) => {
      if (!action) return
      if (action.kind === 'send_message' && action.message) {
        send(action.message)
      } else if (action.kind === 'open_url' && action.url) {
        window.open(action.url, '_blank', 'noopener,noreferrer')
      }
    },
    [send]
  )

  return (
    <>
      {/* Botón flotante (FAB) */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Abrir chat con la concierge virtual"
          style={{
            backgroundColor: theme?.fab_bg || undefined,
            color: theme?.fab_text || undefined,
          }}
          className="group fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-full bg-hilton-700 py-3 pl-3 pr-5 text-white shadow-widget transition hover:opacity-90 active:scale-95 sm:bottom-6 sm:right-6"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15">
            {theme?.emoji
              ? <span style={{ fontSize: 20, lineHeight: 1 }}>{theme.emoji}</span>
              : <MessageCircle size={20} strokeWidth={1.8} />}
          </span>
          <span className="text-sm font-medium tracking-wide">{t.fab}</span>
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
          <div
            className={`flex items-center justify-between px-4 py-5 text-white sm:rounded-t-2xl${theme?.header_bg ? '' : ' bg-hilton-800'}`}
            style={{
              backgroundColor: theme?.header_bg || undefined,
              color: theme?.header_text || undefined,
            }}
          >
            {/* Avatar + info */}
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white/15 ring-2 ring-white/20">
                {theme?.emoji
                  ? <span style={{ fontSize: 22, lineHeight: 1 }}>{theme.emoji}</span>
                  : <Sparkles size={20} strokeWidth={1.5} />}
              </div>
              <div>
                <p className="font-display text-base font-600 tracking-wide leading-none">Aura</p>
                <p className="mt-1 text-xs text-white/60 leading-none">{t.subtitle}</p>
                <p className="mt-1.5 flex items-center gap-1.5 text-xs text-white/80 leading-none">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_6px_1px_rgba(52,211,153,0.7)]" />
                  en línea
                </p>
              </div>
            </div>

            {/* Acciones */}
            <div className="flex items-center">
              {/* Selector de idioma */}
              <div className="relative">
                <button
                  onClick={() => setLangMenu((v) => !v)}
                  aria-label={t.language}
                  title={t.language}
                  aria-haspopup="menu"
                  aria-expanded={langMenu}
                  className="flex h-9 items-center gap-1 rounded-lg px-2 text-white/60 transition hover:bg-white/10 hover:text-white"
                >
                  <Languages size={15} />
                  <span className="text-xs font-semibold tracking-wide">
                    {LANGUAGES.find((l) => l.code === lang)?.short || 'ES'}
                  </span>
                </button>
                {langMenu && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setLangMenu(false)} />
                    <div
                      role="menu"
                      className="absolute right-0 top-11 z-20 w-40 overflow-hidden rounded-xl border border-stone-200 bg-white py-1 text-ink shadow-card-lg"
                    >
                      {LANGUAGES.map((l) => (
                        <button
                          key={l.code}
                          role="menuitem"
                          onClick={() => changeLang(l.code)}
                          className="flex w-full items-center justify-between px-3 py-2 text-sm transition hover:bg-hilton-50"
                        >
                          <span>{l.label}</span>
                          {l.code === lang && <Check size={15} className="text-hilton-600" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {/* Separador */}
              <span className="mx-1 h-5 w-px bg-white/20" />

              <button
                onClick={resetChat}
                disabled={busy || resetting}
                aria-label={t.reset}
                title={t.reset}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-white/50 transition hover:bg-white/10 hover:text-white/90 disabled:opacity-30"
              >
                <RotateCcw size={15} className={resetting ? 'animate-spin' : ''} />
              </button>
              <button
                onClick={() => setOpen(false)}
                aria-label={t.close}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-white/70 transition hover:bg-white/15 hover:text-white"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {/* Mensajes (con capa de efectos estacionales detrás) */}
          <div className="relative flex-1 overflow-hidden bg-white">
            <ChatEffects effect={theme?.effect} />
            <div ref={scrollRef} className="relative z-[1] h-full space-y-3 overflow-y-auto px-4 py-4">
            {messages.map((m, i) => (
              <div key={i} className="space-y-2.5">
                <Bubble role={m.role} accentColor={theme?.accent_color} bubbleBg={theme?.bubble_bg}>{m.content}</Bubble>
                {m.cards?.length > 0 && (
                  <div className="space-y-2.5">
                    {m.cards.map((card, ci) => {
                      if (card.type === 'room')
                        return <RoomCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      if (card.type === 'date_picker')
                        return <DatePickerCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      return null
                    })}
                  </div>
                )}
              </div>
            ))}

            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-md bg-linen px-3 py-2">
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
                    className="self-start rounded-full border border-timber-200 bg-linen px-3.5 py-2 text-left text-xs font-medium text-timber-600 transition hover:border-timber-300 hover:bg-stone-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            </div>
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              send()
            }}
            className="flex items-end gap-2 border-t border-stone-200 bg-white px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
          >
            <textarea
              ref={inputRef}
              value={input}
              rows={1}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                // Enter envía; Shift+Enter hace salto de línea.
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder={t.placeholder}
              className="max-h-32 flex-1 resize-none overflow-y-auto rounded-2xl border border-stone-200 bg-linen px-4 py-2.5 text-sm leading-relaxed text-ink placeholder:text-slatey focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100"
            />
            <button
              type="submit"
              disabled={!input.trim() || busy}
              aria-label="Enviar mensaje"
              style={{ backgroundColor: theme?.accent_color || undefined }}
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white transition hover:opacity-90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50${!theme?.accent_color ? ' bg-hilton-600' : ''}`}
            >
              <Send size={18} />
            </button>
          </form>
        </div>
      )}
    </>
  )
}
