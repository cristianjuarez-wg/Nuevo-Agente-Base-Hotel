import { useEffect, useRef, useState } from 'react'
import { MessageSquare, Globe, Circle, Hand, Bot, Send, Loader2, Info, BedDouble, Trash2 } from 'lucide-react'
import {
  listConversations, takeOverConversation, releaseConversation, sendHumanReply, deleteConversation,
} from '../../services/api'
import { Loading, EmptyState, Badge, formatDateTime, WhatsAppDot } from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import ChatTranscript from '../components/ChatTranscript'
import DetailDrawer from '../components/DetailDrawer'

// Badge según el estado del interlocutor (lo manda el backend en `guest_status`).
function GuestStatusBadge({ status }) {
  if (status === 'in_house') return <Badge tone="green"><BedDouble size={11} className="mr-1" />Alojado ahora</Badge>
  if (status === 'upcoming') return <Badge tone="amber">Reserva futura</Badge>
  if (status === 'customer') return <Badge tone="blue">Cliente</Badge>
  if (status === 'lead') return <Badge tone="gray">Lead</Badge>
  return null  // anónimo: sin badge
}

// "hace X" compacto a partir de un ISO (para el aviso de antigüedad en WhatsApp viejo).
function timeAgo(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 60) return `hace ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `hace ${h} h`
  const d = Math.floor(h / 24)
  return `hace ${d} día${d === 1 ? '' : 's'}`
}

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
  const [profileId, setProfileId] = useState(null)  // contact_id para el drawer 360°
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
    (r.display_name || r.name || '').toLowerCase().includes(q) ||
    (r.phone || '').toLowerCase().includes(q) ||
    (r.last_message_preview || '').toLowerCase().includes(q)
  )

  const selectedConv = rows.find((r) => r.session_id === selected) || null

  const handleDelete = async (sessionId) => {
    try {
      await deleteConversation(sessionId)
      setRows((prev) => prev.filter((r) => r.session_id !== sessionId))
      if (selected === sessionId) setSelected(null)
      toast.success('Conversación eliminada')
    } catch {
      toast.error('No se pudo eliminar la conversación. Intentá de nuevo.')
    }
  }

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
          <ConversationPanel conv={selectedConv}
                             onOpenProfile={selectedConv.contact_id ? () => setProfileId(selectedConv.contact_id) : null}
                             onDelete={handleDelete} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 text-slatey">
            <MessageSquare size={28} className="opacity-40" />
            <p className="text-sm">Elegí una conversación para ver la charla en vivo.</p>
          </div>
        )}
      </div>

      {/* Perfil 360° del contacto (se abre al tocar el nombre). */}
      {profileId && <DetailDrawer contactId={profileId} onClose={() => setProfileId(null)} />}
    </div>
  )
}

// Panel de una conversación: header con control humano, transcripto en vivo y, si está
// tomada, el campo para responder como humano (reemplazando a Aura).
function ConversationPanel({ conv, onOpenProfile, onDelete }) {
  const controlled = !!conv.takeover?.active
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const removeConversation = async () => {
    if (!window.confirm('¿Eliminar esta conversación definitivamente? Se borra el historial de chat (no afecta al contacto ni a sus reservas). Esta acción no se puede deshacer.')) return
    setDeleting(true)
    try {
      await onDelete(conv.session_id)
    } finally {
      setDeleting(false)
    }
  }

  // Chat web sin actividad reciente: el visitante cerró el navegador, no se le puede
  // responder (la respuesta humana web se entrega por WebSocket). WhatsApp no tiene este
  // problema (entrega por Twilio al teléfono).
  const webOffline = conv.channel === 'web' && !conv.is_live
  const waStale = conv.channel === 'whatsapp' && !conv.is_live  // retomar contacto viejo

  const toggleControl = async () => {
    setBusy(true)
    try {
      if (controlled) {
        await releaseConversation(conv.session_id)
        toast.success('Aura retomó la conversación')
      } else {
        await takeOverConversation(conv.session_id)
        toast.success('Tomaste el control — Aura está en pausa')
      }
      // El polling de la lista refrescará el estado en pocos segundos.
    } catch (e) {
      const msg = e?.response?.status === 409
        ? (e?.response?.data?.detail || 'No se puede responder por web: el visitante cerró el chat.')
        : 'No se pudo cambiar el control. Intentá de nuevo.'
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    try {
      await sendHumanReply(conv.session_id, text)
      setDraft('')
    } catch (e) {
      const msg = e?.response?.status === 409
        ? (e?.response?.data?.detail || 'El visitante cerró el chat web; no se puede responder.')
        : 'No se pudo enviar la respuesta.'
      toast.error(msg)
    } finally {
      setSending(false)
    }
  }

  const title = conv.display_name || conv.name || conv.phone || 'Conversación'

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-mist px-5 py-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-serif text-lg font-700 text-hilton-700">
            {onOpenProfile ? (
              <button onClick={onOpenProfile} className="truncate hover:underline" title="Ver perfil 360°">
                {title}
              </button>
            ) : (
              <span className="truncate">{title}</span>
            )}
            <GuestStatusBadge status={conv.guest_status} />
            {conv.is_live && (
              <span className="inline-flex items-center gap-1 text-xs font-sans font-500 text-emerald-600">
                <Circle size={8} className="fill-emerald-500 text-emerald-500" /> En vivo
              </span>
            )}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-sm text-slatey">
            <ChannelBadge channel={conv.channel} phone={conv.phone} />
            {controlled && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-500 text-amber-700">
                <Hand size={11} /> Bajo control humano
              </span>
            )}
            {waStale && !controlled && (
              <span className="text-xs text-slatey/80">· Reanudando contacto · última actividad {timeAgo(conv.last_message_at)}</span>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {webOffline ? (
            <span className="inline-flex max-w-[180px] items-start gap-1.5 rounded-lg bg-mist px-3 py-2 text-xs text-slatey" title="El chat web ya no está activo">
              <Info size={13} className="mt-0.5 shrink-0" /> El visitante cerró el chat. No se puede responder por web.
            </span>
          ) : (
            <button onClick={toggleControl} disabled={busy}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-500 transition disabled:opacity-50 ${
                controlled
                  ? 'bg-hilton-600 text-white hover:bg-hilton-700'
                  : 'border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
              }`}>
              {busy ? <Loader2 size={15} className="animate-spin" />
                : controlled ? <Bot size={15} /> : <Hand size={15} />}
              {controlled ? 'Devolver a Aura' : 'Tomar control'}
            </button>
          )}
          <button onClick={removeConversation} disabled={deleting}
            title="Eliminar conversación definitivamente"
            className="inline-flex items-center justify-center rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
            {deleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
          </button>
        </div>
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
            {r.display_name || r.name || r.phone || 'Visitante web'}
          </span>
          <GuestStatusBadge status={r.guest_status} />
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
