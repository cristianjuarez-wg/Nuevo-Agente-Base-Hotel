import { useEffect, useState, useRef } from 'react'
import { ChevronLeft, ChevronRight, Inbox, TrendingUp, Trophy, XCircle } from 'lucide-react'
import { getKanbanLeads, moveLeadStage } from '../../services/api'
import { OriginBadge, WhatsAppDot, formatNumber } from '../ui'
import { TypeBadge, ScoreBar, LeadChatDrawer, EditLeadModal } from './LeadsView'
import { toast } from '../toast'

// Mapea el lead del kanban (getKanbanLeads) al shape que esperan LeadChatDrawer/EditLeadModal.
// El drawer usa name/type/status/kanbanStage/interest/sessionId; el modal usa firstName/lastName/email/phone.
function toDrawerLead(l) {
  return {
    id: l.id,
    name: l.display_name || l.name || 'Sin nombre',
    firstName: l.name || '',
    lastName: l.last_name || '',
    email: l.email,
    phone: l.phone,
    type: l.lead_type,
    status: l.status,
    kanbanStage: l.kanban_stage,
    interest: l.main_interest,
    sessionId: l.session_id,
  }
}

// Las 4 columnas del tablero, en orden, con su acento (color + texto → no solo color).
const COLUMNS = [
  { id: 'new',       label: 'Nuevo',      accent: 'border-t-hilton-400', count: 'text-hilton-700' },
  { id: 'contacted', label: 'Contactado', accent: 'border-t-amber-400',  count: 'text-amber-700' },
  { id: 'won',       label: 'Ganado',     accent: 'border-t-green-500',  count: 'text-green-700' },
  { id: 'lost',      label: 'Perdido',    accent: 'border-t-red-400',    count: 'text-red-700' },
]

const STAGE_ORDER = COLUMNS.map((c) => c.id)
const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches

function StatChip({ icon: Icon, label, value, tone = 'text-slatey' }) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-white px-3.5 py-2 shadow-card">
      <Icon size={15} className={tone} />
      <span className="text-xs text-slatey">{label}</span>
      <span className={`text-sm font-600 tabular-nums ${tone}`}>{value}</span>
    </div>
  )
}

function LeadCard({ lead, colIndex, onMove, onOpen, dragging, onDragStart, onDragEnd }) {
  const prevStage = STAGE_ORDER[colIndex - 1]
  const nextStage = STAGE_ORDER[colIndex + 1]
  const prevLabel = prevStage && COLUMNS[colIndex - 1].label
  const nextLabel = nextStage && COLUMNS[colIndex + 1].label
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, lead.id)}
      onDragEnd={onDragEnd}
      onClick={() => onOpen(lead)}
      title="Ver y gestionar el lead"
      className={`rounded-2xl bg-white p-4 shadow-card cursor-pointer transition hover:shadow-card-lg active:cursor-grabbing ${
        dragging ? 'opacity-50' : ''
      } ${reduceMotion ? '' : 'transition-all duration-200'}`}
    >
      <p className="font-600 text-ink leading-tight">{lead.display_name || 'Sin nombre'}</p>
      {lead.phone && (
        <p className="mt-1 flex items-center gap-1.5 text-sm text-slatey">
          <span className="tabular-nums">{lead.phone}</span>
          <WhatsAppDot linked={lead.whatsapp_linked} title="Se comunicó por WhatsApp" />
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <TypeBadge type={lead.lead_type} />
        {lead.channel && <OriginBadge origin={lead.channel === 'whatsapp' ? 'aura_whatsapp' : lead.channel === 'instagram' ? 'aura_instagram' : 'aura_web'} />}
      </div>
      <div className="mt-2.5">
        <ScoreBar score={lead.interest_score} />
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-slatey">{lead.time_since_creation || ''}</span>
        {/* Fallback táctil (drag HTML5 no anda en touch): mover de a una etapa. */}
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); prevStage && onMove(lead.id, prevStage) }}
            disabled={!prevStage}
            aria-label={prevLabel ? `Mover a ${prevLabel}` : 'Sin etapa anterior'}
            className="grid h-9 w-9 place-items-center rounded-lg text-slatey transition hover:bg-mist disabled:opacity-30"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); nextStage && onMove(lead.id, nextStage) }}
            disabled={!nextStage}
            aria-label={nextLabel ? `Mover a ${nextLabel}` : 'Sin etapa siguiente'}
            className="grid h-9 w-9 place-items-center rounded-lg text-slatey transition hover:bg-mist disabled:opacity-30"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

function Column({ col, index, leads, dragId, dragOver, onDragStart, onDragEnd, onDragOver, onDrop, onMove, onOpen }) {
  return (
    <div
      onDragOver={(e) => onDragOver(e, col.id)}
      onDrop={(e) => onDrop(e, col.id)}
      className={`w-72 shrink-0 rounded-2xl border-t-2 bg-mist/60 p-3 lg:w-auto lg:flex-1 ${col.accent} ${
        dragOver === col.id ? 'ring-2 ring-hilton-300' : ''
      }`}
    >
      <div className="mb-3 flex items-center justify-between px-1">
        <span className="text-sm font-600 text-ink">{col.label}</span>
        <span className={`text-sm font-600 tabular-nums ${col.count}`}>{leads.length}</span>
      </div>
      <div className="space-y-2.5">
        {leads.length === 0 ? (
          <div className="flex flex-col items-center gap-1.5 rounded-xl border border-dashed border-stone-200 py-8 text-center">
            <Inbox size={20} className="text-stone-300" />
            <span className="text-xs text-slatey">Sin leads acá</span>
          </div>
        ) : (
          leads.map((lead) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              colIndex={index}
              dragging={dragId === lead.id}
              onMove={onMove}
              onOpen={onOpen}
              onDragStart={onDragStart}
              onDragEnd={onDragEnd}
            />
          ))
        )}
      </div>
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-hidden">
      {COLUMNS.map((c) => (
        <div key={c.id} className="w-72 shrink-0 rounded-2xl bg-mist/60 p-3 lg:flex-1">
          <div className="mb-3 h-4 w-20 animate-pulse rounded bg-stone-200" />
          <div className="space-y-2.5">
            {[0, 1].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/70" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function KanbanBoard() {
  const [cols, setCols] = useState({ new: [], contacted: [], won: [], lost: [] })
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dragId, setDragId] = useState(null)
  const [dragOver, setDragOver] = useState(null)
  const [openLead, setOpenLead] = useState(null)   // lead abierto en el panel de gestión
  const [editLead, setEditLead] = useState(null)   // lead en edición (modal)
  const dragFrom = useRef(null)

  const load = () => {
    setLoading(true)
    getKanbanLeads()
      .then(({ columns, stats }) => {
        setCols({ new: columns.new || [], contacted: columns.contacted || [],
                  won: columns.won || [], lost: columns.lost || [] })
        setStats(stats)
      })
      .catch(() => setCols({ new: [], contacted: [], won: [], lost: [] }))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Mueve un lead a otra etapa: optimista (UI al instante), revierte si la API falla.
  const move = async (leadId, toStage) => {
    let fromStage = null
    let card = null
    setCols((prev) => {
      const next = { ...prev }
      for (const s of STAGE_ORDER) {
        const found = next[s].find((l) => l.id === leadId)
        if (found) { fromStage = s; card = found; break }
      }
      if (!card || fromStage === toStage) return prev
      next[fromStage] = next[fromStage].filter((l) => l.id !== leadId)
      next[toStage] = [{ ...card, kanban_stage: toStage }, ...next[toStage]]
      return next
    })
    if (!card || fromStage === toStage) return
    try {
      await moveLeadStage(leadId, toStage)
    } catch {
      toast.error('No se pudo mover el lead. Reintentá.')
      load()  // revertir al estado real del servidor
    }
  }

  const onDragStart = (e, leadId) => {
    setDragId(leadId)
    dragFrom.current = leadId
    e.dataTransfer.effectAllowed = 'move'
  }
  const onDragEnd = () => { setDragId(null); setDragOver(null) }
  const onDragOver = (e, colId) => { e.preventDefault(); setDragOver(colId) }
  const onDrop = (e, colId) => {
    e.preventDefault()
    const id = dragFrom.current
    setDragOver(null); setDragId(null); dragFrom.current = null
    if (id != null) move(id, colId)
  }

  if (loading) return <BoardSkeleton />

  return (
    <div>
      {stats && (
        <div className="mb-4 flex flex-wrap gap-2">
          <StatChip icon={Inbox} label="Total" value={formatNumber(stats.total_leads, 0)} />
          <StatChip icon={TrendingUp} label="Conversión" value={`${stats.conversion_rate}%`} tone="text-hilton-700" />
          <StatChip icon={Trophy} label="Ganados" value={formatNumber(stats.by_stage?.won ?? 0, 0)} tone="text-green-700" />
          <StatChip icon={XCircle} label="Perdidos" value={formatNumber(stats.by_stage?.lost ?? 0, 0)} tone="text-red-700" />
        </div>
      )}
      <div className="flex gap-4 overflow-x-auto pb-2 lg:overflow-x-visible">
        {COLUMNS.map((col, i) => (
          <Column
            key={col.id}
            col={col}
            index={i}
            leads={cols[col.id] || []}
            dragId={dragId}
            dragOver={dragOver}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onMove={move}
            onOpen={setOpenLead}
          />
        ))}
      </div>

      {/* Panel de gestión del lead (bitácora + conversación + editar), reusado de la Lista. */}
      {openLead && (
        <LeadChatDrawer
          lead={toDrawerLead(openLead)}
          onClose={() => setOpenLead(null)}
          onEdit={() => setEditLead(openLead)}
        />
      )}
      {editLead && (
        <EditLeadModal
          lead={toDrawerLead(editLead)}
          onClose={() => setEditLead(null)}
          onSaved={() => { setEditLead(null); setOpenLead(null); load() }}
        />
      )}
    </div>
  )
}
