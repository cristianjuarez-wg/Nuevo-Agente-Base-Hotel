import { useEffect, useRef, useState } from 'react'
import { MessageSquare, Phone, Globe, RefreshCw, Circle } from 'lucide-react'
import { listConversations } from '../../services/api'
import { Loading, EmptyState, formatDateTime, WhatsAppDot } from '../ui'
import SearchInput from '../components/SearchInput'
import ChatTranscript from '../components/ChatTranscript'

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

      {/* Panel derecho: transcripto en vivo */}
      <div className="flex min-w-0 flex-1 flex-col rounded-2xl border border-mist bg-white">
        {selectedConv ? (
          <>
            <div className="flex items-center justify-between border-b border-mist px-5 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-serif text-lg font-700 text-hilton-700">
                  {selectedConv.name || selectedConv.phone || 'Conversación'}
                  {selectedConv.is_live && (
                    <span className="inline-flex items-center gap-1 text-xs font-sans font-500 text-emerald-600">
                      <Circle size={8} className="fill-emerald-500 text-emerald-500" /> En vivo
                    </span>
                  )}
                </p>
                <p className="mt-0.5 flex items-center gap-1.5 text-sm text-slatey">
                  <ChannelBadge channel={selectedConv.channel} phone={selectedConv.phone} />
                </p>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {/* pollMs activo: los mensajes nuevos de la charla abierta aparecen solos */}
              <ChatTranscript sessionId={selectedConv.session_id} pollMs={POLL_MS} />
            </div>
          </>
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
