import { useEffect, useRef, useState } from 'react'
import { MessageSquare, Globe, Circle, Hand, Bot, Send, Loader2 } from 'lucide-react'
import {
  listConversations, takeOverConversation, releaseConversation, sendHumanReply,
} from '../../services/api'
import { Loading, EmptyState, formatDateTime, WhatsAppDot } from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import ChatTranscript from '../components/ChatTranscript'
import { useAdminGate } from '../components/useAdminGate'

// Cada cuánto refrescamos la lista y la charla abierta (polling — bandeja "en vivo").
const POLL_MS = 4000

// Bandeja de conversaciones EN VIVO de ambos canales (web + WhatsApp). Lista a la izquierda
// (con punto verde si hubo actividad reciente), transcripto a la derecha. Refresca por polling:
// los mensajes nuevos aparecen en pocos segundos sin recargar. Solo lectura en esta etapa.
export default function LiveConversationsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)  // session_id abierto
  const firstLoad = useRef(true)

  useEffect(() => {
    let active = true
    const load = () => {
      listConversations('all')
        .then((d) => { if (active) setRows(Array.isArray(d) ? d : []) })
        .catch(() => { if (active && firstLoad.current) setRows([]) })
        .finally(() => { if (active) { setLoading(false); firstLoad.current = false } })
    }
    load()
    const id = setInterval(load, POLL_MS)
    return () => { active = false; clearInterval(id) }
  }, [])

  const q = query.trim().toLowerCase()
  const filtered = !q ? rows : rows.filter((r) =>
    (r.name || '').toLowerCase().includes(q) ||
    (r.phone || '').toLowerCase().includes(q) ||
    (r.last_message_preview || '').toLowerCase().includes(q)
  )

  const selectedConv = rows.find((r) => r.session_id === selected) || null

  if (loading) return <Loading label="Cargando conversaciones…" />

  return (
    <div className="flex h-[calc(100dvh-180px)] min-h-[420px] gap-4">
      {/* Panel izquierdo: lista de conversaciones */}
      <div className="flex w-full max-w-sm shrink-0 flex-col rounded-2xl border border-mist bg-white">
        <div className="border-b border-mist p-3">
          <SearchInput value={query} onChange={setQuery} placeholder="Buscar por nombre, teléfono o mensaje…" />
        </div>
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <EmptyState icon={MessageSquare} title="Sin conversaciones"
                        desc="Cuando alguien escriba por web o WhatsApp, aparecerá acá." />
          ) : (
            filtered.map((r) => (
              <ConversationRow key={r.session_id} r={r}
                               active={r.session_id === selected}
                               onClick={() => setSelected(r.session_id)} />
            ))
          )}
        </div>
      </div>

      {/* Panel derecho: transcripto en vivo + control humano */}
      <div className="flex min-w-0 flex-1 flex-col rounded-2xl border border-mist bg-white">
        {selectedConv ? (
          <ConversationPanel conv={selectedConv} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-slatey">
            <MessageSquare size={28} className="opacity-40" />
            <p className="text-sm">Elegí una conversación para ver la charla en vivo.</p>
          </div>
        )}
      </div>
    </div>
  )
}

// Panel de una conversación: header con control humano, transcripto en vivo y, si está
// tomada, el campo para responder como humano (reemplazando a Aura).
function ConversationPanel({ conv }) {
  const controlled = !!conv.takeover?.active
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  // Las acciones de takeover son críticas (X-Admin-Key). runProtected abre el modal de clave
  // ante un 403 y reintenta la acción al confirmarla.
  const { runProtected, gateModal } = useAdminGate()

  const toggleControl = async () => {
    setBusy(true)
    try {
      await runProtected(async () => {
        if (controlled) {
          await releaseConversation(conv.session_id)
          toast.success('Aura retomó la conversación')
        } else {
          await takeOverConversation(conv.session_id)
          toast.success('Tomaste el control — Aura está en pausa')
        }
      })
      // El polling de la lista refrescará el estado en pocos segundos.
    } catch {
      toast.error('No se pudo cambiar el control. Intentá de nuevo.')
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    try {
      await runProtected(async () => {
        await sendHumanReply(conv.session_id, text)
        setDraft('')
      })
    } catch {
      toast.error('No se pudo enviar la respuesta.')
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-mist px-5 py-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-serif text-lg font-700 text-hilton-700">
            {conv.name || conv.phone || 'Conversación'}
            {conv.is_live && (
              <span className="inline-flex items-center gap-1 text-xs font-sans font-500 text-emerald-600">
                <Circle size={8} className="fill-emerald-500 text-emerald-500" /> En vivo
              </span>
            )}
          </p>
          <p className="mt-0.5 flex items-center gap-1.5 text-sm text-slatey">
            <ChannelBadge channel={conv.channel} phone={conv.phone} />
            {controlled && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-500 text-amber-700">
                <Hand size={11} /> Bajo control humano
              </span>
            )}
          </p>
        </div>
        <button onClick={toggleControl} disabled={busy}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-500 transition disabled:opacity-50 ${
            controlled
              ? 'bg-hilton-600 text-white hover:bg-hilton-700'
              : 'border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
          }`}>
          {busy ? <Loader2 size={15} className="animate-spin" />
            : controlled ? <Bot size={15} /> : <Hand size={15} />}
          {controlled ? 'Devolver a Aura' : 'Tomar control'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <ChatTranscript sessionId={conv.session_id} pollMs={POLL_MS} />
      </div>

      {controlled && (
        <div className="border-t border-mist p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              rows={1}
              placeholder="Escribí tu respuesta como humano…"
              className="max-h-32 min-h-[42px] flex-1 resize-none rounded-xl border border-mist px-3.5 py-2.5 text-sm focus:border-hilton-400 focus:outline-none"
            />
            <button onClick={send} disabled={!draft.trim() || sending}
              className="inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-xl bg-hilton-600 text-white transition hover:bg-hilton-700 disabled:opacity-50">
              {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
          <p className="mt-1.5 px-1 text-[11px] text-slatey">
            Tu mensaje se le envía al huésped{conv.channel === 'whatsapp' ? ' por WhatsApp' : ''}. Aura no responderá hasta que la liberes.
          </p>
        </div>
      )}
      {gateModal}
    </>
  )
}

// Fila de la lista: nombre/teléfono, canal, punto "en vivo", preview del último mensaje.
function ConversationRow({ r, active, onClick }) {
  return (
    <button onClick={onClick}
      className={`flex w-full flex-col gap-1 border-b border-mist px-4 py-3 text-left transition hover:bg-hilton-50/50 ${
        active ? 'bg-hilton-50' : ''
      }`}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          {r.is_live && <Circle size={8} className="shrink-0 fill-emerald-500 text-emerald-500" />}
          <span className="truncate font-medium text-ink">
            {r.name || r.phone || 'Sin nombre'}
          </span>
        </span>
        <span className="shrink-0 text-[11px] tabular-nums text-slatey">{formatDateTime(r.last_message_at)}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-slatey">
          {r.last_message_role === 'user' ? '' : 'Aura: '}{r.last_message_preview || '—'}
        </span>
        <ChannelBadge channel={r.channel} phone={r.phone} compact />
      </div>
    </button>
  )
}

// Indicador de canal: WhatsApp (punto verde) o Web (globo).
function ChannelBadge({ channel, phone, compact = false }) {
  if (channel === 'whatsapp') {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 text-xs text-slatey">
        <WhatsAppDot linked title="WhatsApp" />
        {!compact && <>{phone || 'WhatsApp'}</>}
      </span>
    )
  }
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs text-slatey">
      <Globe size={13} className="text-hilton-500" />{!compact && 'Chat web'}
    </span>
  )
}
