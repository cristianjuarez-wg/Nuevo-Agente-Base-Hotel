import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MessageCircle, X, Send, Sparkles, RotateCcw, Languages, Check, Info } from 'lucide-react'
import HelpModal from './HelpModal'
import { getGreeting, sendMessage, clearChat, getChatTheme, chatWsUrl } from '../services/api'
import RoomCard from './chat/RoomCard'
import DatePickerCard from './chat/DatePickerCard'
import MenuCard from './chat/MenuCard'
import MenuOrderCard from './chat/MenuOrderCard'
import TableReservationCard from './chat/TableReservationCard'
import ChatEffects from './chat/ChatEffects'
import { LANGUAGES, getStrings, detectInitialLang, persistLang } from '../i18n/chat'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

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

// Indicador de espera: puntitos + una frase cálida que rota mientras el backend trabaja
// (triage + tools tardan, así la espera no se siente muerta). `phrases` viene de i18n.
function ThinkingIndicator({ phrases }) {
  const list = Array.isArray(phrases) && phrases.length ? phrases : ['…']
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    if (list.length < 2) return
    const t = setInterval(() => setIdx((i) => (i + 1) % list.length), 1800)
    return () => clearInterval(t)
  }, [list.length])
  return (
    <div className="flex items-center gap-2 px-1 py-1">
      <TypingDots />
      <span className="text-xs text-slatey/70">{list[idx]}</span>
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
  const [busy, setBusy] = useState(false)      // ciclo completo (espera + escritura)
  const [waiting, setWaiting] = useState(false) // solo mientras espera al backend
  const [greeted, setGreeted] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)  // modal "¿Qué puede hacer Aura?"
  const [theme, setTheme] = useState(null)
  const [lang, setLang] = useState(detectInitialLang)
  const [langMenu, setLangMenu] = useState(false)
  const scrollRef = useRef(null)
  const anchorRef = useRef(null)  // ancla al inicio del último turno del usuario (para posicionar la vista)
  const pickerRef = useRef(null)  // card del date picker más reciente (para traerla a la vista cuando aparece)
  const inputRef = useRef(null)
  const sessionId = useRef(getSessionId())
  const typewriterRef = useRef(null)  // timer del efecto de tipeo (para poder cancelarlo)
  const wsRef = useRef(null)          // WebSocket de mensajes humanos en vivo (takeover)
  const seenHumanRef = useRef(new Set())  // dedupe de respuestas humanas recibidas por WS
  // id incremental para keys ESTABLES de los mensajes (no usar el índice del array). Las keys
  // por índice causaban un bug visual: al crecer el texto del typewriter y luego reemplazarlo
  // (finish), React reconciliaba por posición y dejaba el fragmento parcial como un mensaje
  // aparte (se veía el texto cortado + el completo). Con id estable cada burbuja es un nodo fijo.
  const msgSeq = useRef(0)
  const sendingRef = useRef(false)   // candado SÍNCRONO anti doble-envío (busy es estado async)
  // Identidad del negocio para interpolar {businessName}/{city} en los textos del widget (P2).
  const profile = useBusinessProfile()
  const i18nVars = { businessName: profile.name, city: profile.city }
  const t = getStrings(lang, i18nVars)

  // Inyecta una respuesta HUMANA (asesor que tomó la conversación), recibida por WebSocket.
  // Deduplica por `key` (contenido) y no agrega si ese contenido ya está visible. Reutiliza el
  // mismo render que un mensaje de Aura.
  const injectHumanMessage = useCallback((content, key) => {
    if (!content) return
    const k = String(key ?? content)
    if (seenHumanRef.current.has(k)) return
    seenHumanRef.current.add(k)
    setMessages((m) => {
      if (m.some((x) => x.role === 'assistant' && x.content === content)) return m  // ya visible
      return [...m, { id: `m${++msgSeq.current}`, role: 'assistant', content, fromHuman: true }]
    })
    if (typewriterRef.current) clearTimeout(typewriterRef.current)
    setWaiting(false)
    setBusy(false)
  }, [])

  // Cargar tema visual una sola vez al montar
  useEffect(() => {
    getChatTheme().then(setTheme).catch(() => {})
  }, [])

  const loadGreeting = useCallback((forLang) => {
    const useLang = forLang || lang
    setGreeted(true)
    getGreeting(useLang)
      .then((data) => {
        setMessages([{ id: `m${++msgSeq.current}`, role: 'assistant', content: data.greeting }])
        // Los starters vienen del perfil (español); solo se muestran en ES para no mezclar.
        setStarters(useLang === 'es' ? (data.conversation_starters?.slice(0, 4) || []) : [])
      })
      .catch(() =>
        setMessages([{ id: `m${++msgSeq.current}`, role: 'assistant', content: getStrings(useLang, i18nVars).greetingFallback }])
      )
  }, [lang])

  // Cambiar idioma: persiste, reinicia el saludo en el nuevo idioma y limpia la sesión
  // en el backend para que Aura siga 100% en el idioma elegido.
  const changeLang = useCallback((code) => {
    if (code === lang) { setLangMenu(false); return }
    if (typewriterRef.current) clearTimeout(typewriterRef.current)
    setBusy(false); setWaiting(false)
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

  // Canal en vivo para respuestas HUMANAS (cuando un asesor toma la conversación). Mientras el
  // widget está abierto: WebSocket con reconexión por backoff. Solo recibe mensajes humanos
  // (type "human_message"); las respuestas normales de Aura llegan por HTTP y NO pasan por acá.
  useEffect(() => {
    if (!open) return
    let closed = false
    let ws = null
    let reconnectTimer = null
    let attempt = 0

    const connect = () => {
      if (closed) return
      try {
        ws = new WebSocket(chatWsUrl(sessionId.current))
        wsRef.current = ws
      } catch {
        scheduleReconnect()
        return
      }
      ws.onopen = () => { attempt = 0 }
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data?.type === 'human_message') injectHumanMessage(data.content, data.content)
        } catch { /* ignorar frames no-JSON (ping/keepalive) */ }
      }
      ws.onclose = () => { if (!closed) scheduleReconnect() }
      ws.onerror = () => { try { ws.close() } catch { /* noop */ } }
    }

    const scheduleReconnect = () => {
      if (closed) return
      const delay = Math.min(1000 * 2 ** attempt, 15000)  // 1s,2s,4s,8s… máx 15s
      attempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    connect()

    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      try { ws && ws.close() } catch { /* noop */ }
      wsRef.current = null
    }
  }, [open, injectHumanMessage])

  // Posicionar la vista al COMIENZO del último turno del usuario cuando manda un mensaje.
  // Así la respuesta de Aura (texto + cards) se revela debajo y se lee desde arriba, sin
  // saltar al fondo (antes el scroll iba a scrollHeight y había que subir con respuestas largas).
  const userMsgCount = messages.filter((m) => m.role === 'user').length
  const lastUserIndex = messages.map((m) => m.role).lastIndexOf('user')
  useEffect(() => {
    if (anchorRef.current) {
      anchorRef.current.scrollIntoView({ block: 'start', behavior: 'smooth' })
    } else {
      // Sin ancla (ej. solo el saludo): mantené la vista al final.
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [userMsgCount])

  // Mientras Aura escribe, seguí el final SOLO si el usuario ya está cerca del fondo (no lo
  // arrancamos de la lectura si subió). El ancla de arriba gobierna la posición principal.
  useEffect(() => {
    const el = scrollRef.current
    if (!el || !busy) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (nearBottom) el.scrollTo({ top: el.scrollHeight })
  }, [messages, busy])

  // Cuando el último turno de Aura trae el DATE PICKER, traelo a la vista completo (incluido su
  // botón de confirmar). El picker llega DESPUÉS del texto (typeOutReply lo adjunta al final del
  // tipeo), así que reaccionamos a [messages]; sin esto la card queda debajo del fold y el usuario
  // responde la fecha por texto sin completar el picker.
  const lastMsg = messages[messages.length - 1]
  const lastHasPicker = lastMsg?.role === 'assistant' && lastMsg.cards?.some((c) => c.type === 'date_picker')
  useEffect(() => {
    if (lastHasPicker) {
      pickerRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
    }
  }, [lastHasPicker])

  // Auto-resize del textarea: crece con el contenido hasta max-h (128px = max-h-32) y recién
  // ahí muestra scroll. Sin esto, overflow-y-auto fijo pintaba el scrollbar aun vacío (por
  // redondeo subpíxel del padding/interlineado).
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    const max = 128  // px — coincide con la clase max-h-32
    el.style.height = `${Math.min(el.scrollHeight, max)}px`
    el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
  }, [input])

  // Revela el texto del agente palabra por palabra (efecto de tipeo). Si el usuario
  // prefiere menos movimiento, lo muestra completo de una. Adjunta las cards al final.
  const typeOutReply = useCallback((fullText, cards) => {
    const sessionAtStart = sessionId.current
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    // Mensaje assistant vacío al que le vamos creciendo el contenido. Id estable: lo
    // preservamos al reemplazar (finish/revealed) para que React lo trate como el MISMO nodo.
    const bubble = { id: `m${++msgSeq.current}`, role: 'assistant', content: '', cards: [] }
    setMessages((m) => [...m, bubble])

    const finish = (content) => {
      setMessages((m) => {
        const next = [...m]
        next[next.length - 1] = { ...bubble, content, cards: cards || [] }
        return next
      })
      setBusy(false)
      sendingRef.current = false  // liberar el candado anti doble-envío
      inputRef.current?.focus()
    }

    if (reduceMotion || !fullText) { finish(fullText || '…'); return }

    const words = fullText.split(/(\s+)/)  // conserva los espacios como tokens
    // Ritmo adaptativo: en textos largos revelamos más tokens por tick para que la
    // escritura nunca dure de más (tope ~3-4s); en cortos, 2 tokens (palabra+espacio).
    const perTick = words.length > 80 ? 6 : words.length > 40 ? 4 : 2
    let i = 0
    const step = () => {
      // Si la conversación se reseteó/cambió de idioma a mitad, cortamos sin escribir.
      if (sessionId.current !== sessionAtStart) { setBusy(false); sendingRef.current = false; return }
      i += perTick
      const revealed = words.slice(0, i).join('')
      if (i >= words.length) {
        finish(fullText)
        return
      }
      setMessages((m) => {
        const next = [...m]
        next[next.length - 1] = { ...next[next.length - 1], content: revealed }
        return next
      })
      typewriterRef.current = setTimeout(step, 30)
    }
    step()
  }, [])

  const send = useCallback(
    async (text) => {
      const msg = (text ?? input).trim()
      // Candado SÍNCRONO: el textarea dentro del <form> puede disparar Enter (onKeyDown) y
      // submit casi a la vez; `busy` es estado async y no frena la segunda llamada en el mismo
      // tick. El ref sí (se setea ya). Se libera cuando termina el typewriter o ante un error.
      if (!msg || busy || sendingRef.current) return
      sendingRef.current = true
      setStarters([])
      setInput('')
      setMessages((m) => [...m, { id: `m${++msgSeq.current}`, role: 'user', content: msg }])
      setBusy(true)
      setWaiting(true)
      try {
        const data = await sendMessage({ message: msg, sessionId: sessionId.current, language: lang })
        setWaiting(false)
        typeOutReply(data.response || '…', data.cards || [])
      } catch {
        setWaiting(false)
        setMessages((m) => [
          ...m,
          { id: `m${++msgSeq.current}`, role: 'assistant', content: getStrings(lang).errorReply },
        ])
        setBusy(false)
        sendingRef.current = false
        inputRef.current?.focus()
      }
    },
    [input, busy, lang, typeOutReply]
  )

  // Retorno desde la pantalla de pedido: si el hash trae ?order=RST-XXXX, abrimos el chat
  // y le avisamos al agente para que registre/confirme el pedido. Se hace una sola vez.
  useEffect(() => {
    const m = window.location.hash.match(/[?&]order=([A-Za-z0-9-]+)/)
    if (!m) return
    const code = m[1]
    // Limpia el parámetro del hash para no re-disparar al recargar.
    window.location.hash = 'inicio'
    setOpen(true)
    const t = setTimeout(() => {
      send(`Listo, confirmo mi pedido del restaurante (código ${code}).`)
    }, 600)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const resetChat = useCallback(async () => {
    if (busy || resetting) return
    if (typewriterRef.current) clearTimeout(typewriterRef.current)
    setWaiting(false)
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

  // Cleanup: cancelar el typewriter si el componente se desmonta.
  useEffect(() => () => { if (typewriterRef.current) clearTimeout(typewriterRef.current) }, [])

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
        <div className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-white animate-slide-up-widget sm:inset-auto sm:bottom-6 sm:right-6 sm:h-[600px] sm:max-h-[85vh] sm:w-[400px] sm:rounded-2xl sm:shadow-widget">
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
              {/* Ayuda: qué puede hacer Aura (encauza expectativas) */}
              <button
                onClick={() => setHelpOpen(true)}
                aria-label={t.helpOpen}
                title={t.helpOpen}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white"
              >
                <Info size={16} />
              </button>

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
                title={t.resetHint}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-sand-300 transition hover:bg-white/10 hover:text-sand-200 disabled:opacity-30"
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
            {messages.map((m, i) => {
              // El último mensaje del usuario es el ancla: al enviarlo, la vista se posiciona
              // con ese turno arriba, para leer la respuesta de Aura desde el comienzo.
              const isLastUser = m.role === 'user' && i === lastUserIndex
              return (
              <div key={m.id ?? i} ref={isLastUser ? anchorRef : null} className="space-y-2.5">
                <Bubble role={m.role} accentColor={theme?.accent_color} bubbleBg={theme?.bubble_bg}>{m.content}</Bubble>
                {m.cards?.length > 0 && (
                  <div className="space-y-2.5">
                    {m.cards.map((card, ci) => {
                      if (card.type === 'room')
                        return <RoomCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      if (card.type === 'date_picker')
                        return <div key={ci} ref={pickerRef}><DatePickerCard card={card} onAction={handleCardAction} lang={lang} /></div>
                      if (card.type === 'menu_interactive')
                        return <MenuOrderCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      if (card.type === 'table_reservation')
                        return <TableReservationCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      if (card.type === 'menu')
                        return <MenuCard key={ci} card={card} onAction={handleCardAction} lang={lang} />
                      return null
                    })}
                  </div>
                )}
              </div>
              )
            })}

            {waiting && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-md bg-linen px-3 py-2">
                  <ThinkingIndicator phrases={t.thinking} />
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

            {/* Acceso al modal de ayuda: solo al inicio (antes de conversar), para encauzar
                qué tiene sentido preguntarle a Aura. Más visible que el ícono del header. */}
            {messages.length <= 1 && !busy && (
              <button
                onClick={() => setHelpOpen(true)}
                className="mt-1 inline-flex items-center gap-1.5 self-start text-xs font-medium text-timber-600 underline decoration-timber-300 underline-offset-2 transition hover:text-timber-700"
              >
                <Info size={13} /> {t.helpOpen}
              </button>
            )}

            {/* Aviso de sesión: la charla se recuerda 24 h salvo que se reinicie. Solo al
                inicio, para que quien prueba la demo no se confunda si Aura "recuerda" lo previo. */}
            {messages.length <= 1 && !busy && (
              <p className="mt-1 flex items-start gap-1.5 self-start text-[11px] leading-snug text-slatey/70">
                <RotateCcw size={11} className="mt-0.5 shrink-0 text-sand-500" />
                {t.sessionHint}
              </p>
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
              className="max-h-32 flex-1 resize-none overflow-hidden rounded-2xl border border-stone-200 bg-linen px-4 py-2.5 text-sm leading-relaxed text-ink placeholder:text-slatey focus:border-hilton-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-hilton-100"
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

          {/* Modal "¿Qué puede hacer Aura?" — encauza expectativas (qué sí, ejemplos, qué no). */}
          {helpOpen && (
            <HelpModal
              t={t}
              onClose={() => setHelpOpen(false)}
              onAsk={(text) => { setHelpOpen(false); send(text) }}
            />
          )}
        </div>
      )}
    </>
  )
}
