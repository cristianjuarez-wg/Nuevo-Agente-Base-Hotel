import { useEffect, useState } from 'react'
import { MessageSquare, RefreshCw, Trash2, X, Phone } from 'lucide-react'
import { listConversations, deleteContact, clearConversationByPhone } from '../../services/api'
import { ResponsiveTable, Badge, Loading, EmptyState, formatDate, WhatsAppDot } from '../ui'
import { toast } from '../toast'
import SearchInput from '../components/SearchInput'
import Pagination from '../components/Pagination'
import ChatTranscript from '../components/ChatTranscript'
import { useTableControls } from '../hooks/useTableControls'

// Conversaciones de WhatsApp: muestra quién se contactó (aunque no haya dejado nombre ni
// reserva). El histórico existe en la DB; esta vista lo hace visible y permite borrarlo.
export default function ConversationsView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [deletingKey, setDeletingKey] = useState(null)
  const [chat, setChat] = useState(null)  // conversación cuyo histórico se está viendo

  const load = () => {
    setLoading(true)
    listConversations('whatsapp')
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const remove = async (r) => {
    const label = r.name || r.phone || 'esta conversación'
    if (!window.confirm(`¿Eliminar a ${label} y borrar todo su historial de chat? El agente dejará de reconocerlo. Esta acción no se puede deshacer.`)) return
    setDeletingKey(r.session_id)
    try {
      // Borramos SIEMPRE por teléfono: limpia el historial de la charla esté o no vinculada a
      // un Contact (las conversaciones de WhatsApp suelen quedar con contact_id=None) y limpia
      // la memoria del agente. Si además hay un Contact, lo eliminamos para no dejarlo huérfano.
      if (r.phone) await clearConversationByPhone(r.phone)
      if (r.contact_id) await deleteContact(r.contact_id)
      setRows((prev) => prev.filter((x) => x.session_id !== r.session_id))
      toast.success('Conversación eliminada')
    } catch {
      toast.error('No se pudo eliminar. Intentá de nuevo.')
    } finally {
      setDeletingKey(null)
    }
  }

  const NameCell = ({ r }) => (
    r.name
      ? <span className="font-medium text-ink">{r.name}</span>
      : <span className="text-sm text-slatey italic">Sin nombre</span>
  )

  const PhoneCell = ({ r }) => (
    <span className="inline-flex items-center gap-1.5 tabular-nums text-ink">
      <Phone size={13} className="text-hilton-500" />{r.phone || '—'}
      <WhatsAppDot linked title="Conversación por WhatsApp" />
    </span>
  )

  const DeleteBtn = ({ r }) => (
    <button onClick={() => remove(r)} disabled={deletingKey === r.session_id} title="Eliminar y borrar historial"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50">
      <Trash2 size={15} />
    </button>
  )

  const columns = [
    { key: 'phone', label: 'Teléfono', render: (r) => <PhoneCell r={r} /> },
    { key: 'name', label: 'Nombre', render: (r) => <NameCell r={r} /> },
    { key: 'message_count', label: 'Mensajes', render: (r) => <span className="tabular-nums">{r.message_count ?? 0}</span> },
    { key: 'last_message_at', label: 'Último mensaje', sortable: true, render: (r) => formatDate(r.last_message_at) },
    { key: 'lead', label: '', render: (r) => (
      r.lead_generated ? <Badge tone="green">Lead</Badge> : null
    ) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1">
        <button onClick={() => setChat(r)} title="Ver conversación"
          className="rounded-lg p-1.5 text-slatey transition hover:bg-hilton-50 hover:text-hilton-700">
          <MessageSquare size={15} />
        </button>
        <DeleteBtn r={r} />
      </div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <PhoneCell r={r} />
        {r.lead_generated ? <Badge tone="green">Lead</Badge> : null}
      </div>
      <NameCell r={r} />
      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-slatey">{r.message_count ?? 0} mensajes · {formatDate(r.last_message_at)}</span>
        <div className="flex items-center gap-1">
          <button onClick={() => setChat(r)} className="rounded-lg p-1.5 text-slatey hover:bg-hilton-50 hover:text-hilton-700"><MessageSquare size={15} /></button>
          <DeleteBtn r={r} />
        </div>
      </div>
    </div>
  )

  const { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize } = useTableControls(rows, {
    searchKeys: ['phone', 'name'],
    pageSize: 50,
    sortAccessors: { last_message_at: (r) => r.last_message_at || '' },
  })

  if (loading) return <Loading label="Cargando conversaciones…" />

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-slatey">
          Quién se contactó por WhatsApp — incluso sin dejar datos. Tocá una fila para ver la charla.
        </p>
        <button onClick={load} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>
      </div>

      {rows.length === 0 ? (
        <EmptyState icon={MessageSquare} title="Sin conversaciones de WhatsApp"
                    desc="Cuando alguien escriba por WhatsApp, su charla aparecerá acá." />
      ) : (
        <>
          <div className="mb-4"><SearchInput value={query} onChange={setQuery} placeholder="Buscar por teléfono o nombre…" /></div>
          <ResponsiveTable
            columns={columns}
            rows={pageRows.map((r) => ({ ...r, _key: r.session_id }))}
            renderCard={renderCard}
            sort={sort}
            onSort={toggleSort}
          />
          <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
        </>
      )}

      {chat && <ConversationDrawer conv={chat} onClose={() => setChat(null)} />}
    </div>
  )
}

// Panel lateral con el histórico de la charla (reutiliza ChatTranscript por session_id).
function ConversationDrawer({ conv, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-card-lg animate-slide-up">
        <div className="flex items-start justify-between border-b border-mist px-5 py-4">
          <div>
            <p className="font-serif text-lg font-700 text-hilton-700">{conv.name || conv.phone || 'Conversación'}</p>
            <p className="mt-0.5 flex items-center gap-1.5 text-sm text-slatey">
              {conv.phone}<WhatsAppDot linked title="WhatsApp" /> · Conversación con Aura
            </p>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ChatTranscript sessionId={conv.session_id} />
        </div>
      </aside>
    </div>
  )
}
