import { useEffect, useState } from 'react'
import {
  Mail, Phone, X, BedDouble, CalendarCheck,
  DollarSign, Star, Loader2, UtensilsCrossed, Receipt, Pencil, Save, LifeBuoy,
  MessageSquare, MessageCircle, Globe, ChevronLeft, ChevronRight, CheckCircle2,
} from 'lucide-react'
import { getGuestProfile, updateGuestPreferences, getFolio, updateContact, getContactConversations } from '../../services/api'
import { Badge, OriginBadge, Loading, formatDate, formatUSD } from '../ui'
import { toast } from '../toast'
import ChatTranscript from './ChatTranscript'

// Estado de un ticket (consulta/reclamo) → badge. Compartido por la lista y el detalle.
function ticketStatusBadge(t) {
  if (t.status === 'resolved') return { tone: 'green', label: 'Resuelto' }
  if (t.status === 'escalated' || t.escalated) return { tone: 'red', label: 'Escalado' }
  if (t.status === 'in_progress') return { tone: 'blue', label: 'En curso' }
  return { tone: 'amber', label: 'Abierto' }
}

const TICKET_CATEGORY_LABELS = {
  info: 'Información', change: 'Cambio', cancel: 'Cancelación', complaint: 'Reclamo',
  general: 'General', service_request: 'Servicio',
}

// ── Panel de detalle 360° (drawer lateral) ───────────────────────────────────
function ProfileStat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl bg-mist px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs text-slatey"><Icon size={13} /> {label}</div>
      <p className="mt-0.5 font-serif text-base font-700 tabular-nums text-ink">{value}</p>
    </div>
  )
}

function PreferenceEditor({ profile, onSave, saving }) {
  const prefs = profile.preferences || {}
  const [allergies, setAllergies] = useState((prefs.allergies || []).join(', '))
  const [dietary, setDietary] = useState((prefs.dietary || []).join(', '))
  const [services, setServices] = useState((prefs.services_used || []).join(', '))
  const [notes, setNotes] = useState(prefs.notes || '')

  const toList = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

  return (
    <div className="space-y-3">
      <Field label="⚠️ Alergias / intolerancias" hint="seguridad alimentaria — separadas por coma">
        <input className="w-full rounded-xl border border-red-200 bg-red-50/40 px-3.5 py-2.5 text-sm focus:border-red-400 focus:outline-none"
               value={allergies} onChange={(e) => setAllergies(e.target.value)}
               placeholder="maní, frutos secos, mariscos" />
      </Field>
      <Field label="Preferencias dietéticas" hint="separadas por coma">
        <input className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
               value={dietary} onChange={(e) => setDietary(e.target.value)}
               placeholder="vegetariano, sin TACC" />
      </Field>
      <Field label="Servicios que suele usar" hint="separados por coma">
        <input className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
               value={services} onChange={(e) => setServices(e.target.value)}
               placeholder="guarda-skis, cochera" />
      </Field>
      <Field label="Notas del hotel">
        <textarea className="w-full min-h-[64px] rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
                  value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Prefiere pisos altos, viaja con mascota…" />
      </Field>
      <button
        onClick={() => onSave({ ...prefs, allergies: toList(allergies), dietary: toList(dietary), services_used: toList(services), notes })}
        disabled={saving}
        className="btn-primary w-full py-2.5 text-sm disabled:opacity-60"
      >
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Star size={15} />}
        Guardar preferencias
      </button>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink">
        {label} {hint && <span className="font-normal text-slatey">({hint})</span>}
      </span>
      {children}
    </label>
  )
}

export default function DetailDrawer({ contactId, onClose }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [folio, setFolio] = useState(null)
  const [conversations, setConversations] = useState([])
  const [openChat, setOpenChat] = useState(null)  // conversación abierta en la transcripción
  const [selectedTicket, setSelectedTicket] = useState(null)  // consulta/reclamo abierto en su detalle

  useEffect(() => {
    setLoading(true)
    setFolio(null)
    setConversations([])
    setOpenChat(null)
    setSelectedTicket(null)
    getGuestProfile(contactId)
      .then((p) => {
        setProfile(p)
        // Si está hospedado, traemos su folio (estadía + consumos).
        const code = p?.active_stay?.code
        if (code) getFolio(code).then(setFolio).catch(() => setFolio(null))
      })
      .catch(() => setProfile(null))
      .finally(() => setLoading(false))
    // Todas las conversaciones del huésped (web y WhatsApp), para verlas desde el perfil.
    getContactConversations(contactId).then(setConversations).catch(() => setConversations([]))
  }, [contactId])

  const save = async (preferences) => {
    setSaving(true)
    try {
      await updateGuestPreferences(contactId, preferences)
      const fresh = await getGuestProfile(contactId)
      setProfile(fresh)
      toast.success('Preferencias guardadas')
    } catch {
      toast.error('No se pudieron guardar las preferencias')
    } finally {
      setSaving(false)
    }
  }

  const [editing, setEditing] = useState(false)
  const saveContact = async (fields) => {
    try {
      await updateContact(contactId, fields)
      const fresh = await getGuestProfile(contactId)
      setProfile(fresh)
      setEditing(false)
      toast.success('Datos del pasajero actualizados')
    } catch (e) {
      const msg = e?.response?.data?.detail || 'No se pudieron guardar los datos.'
      toast.error(msg)
      throw e
    }
  }

  const c = profile?.contact || {}
  const name = c.full_name || [c.first_name, c.last_name].filter(Boolean).join(' ') || 'Huésped'

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-linen shadow-card-lg animate-slide-up">
        <header className="flex items-center justify-between border-b border-hilton-100 bg-white px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate font-serif text-lg font-700 text-ink">{name}</h2>
            {profile?.origin && <div className="mt-0.5"><OriginBadge origin={profile.origin} /></div>}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setEditing(true)} aria-label="Editar datos" title="Editar datos"
                    className="flex h-10 w-10 items-center justify-center rounded-lg text-slatey hover:bg-mist hover:text-ink">
              <Pencil size={17} />
            </button>
            <button onClick={onClose} aria-label="Cerrar"
                    className="flex h-10 w-10 items-center justify-center rounded-lg text-slatey hover:bg-mist">
              <X size={20} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <Loading />
          ) : !profile ? (
            <p className="text-sm text-slatey">No se pudo cargar el perfil.</p>
          ) : (
            <div className="space-y-5">
              {profile.is_staying_now && (
                <div className="flex items-center gap-2 rounded-xl bg-green-50 px-4 py-3 text-sm font-medium text-green-700">
                  <BedDouble size={16} /> Alojado actualmente
                  {profile.active_stay?.room_number && (
                    <span className="rounded bg-green-600 px-2 py-0.5 text-xs font-semibold tabular-nums text-white">
                      Hab. {profile.active_stay.room_number}
                    </span>
                  )}
                  {profile.active_stay?.code && <span className="tabular-nums opacity-80">· {profile.active_stay.code}</span>}
                </div>
              )}

              {/* Alergias resaltadas (seguridad alimentaria) */}
              {profile.preferences?.allergies?.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  <span className="font-semibold">⚠️ Alergias:</span>
                  {profile.preferences.allergies.map((a) => (
                    <span key={a} className="rounded-full bg-red-600/90 px-2.5 py-0.5 text-xs font-medium text-white">{a}</span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <ProfileStat icon={CalendarCheck} label="Estadías" value={profile.stays_count} />
                <ProfileStat icon={DollarSign} label="Gasto alojamiento"
                             value={formatUSD(profile.total_spent_usd || 0)} />
                <ProfileStat icon={UtensilsCrossed} label="Gasto restaurante"
                             value={formatUSD(profile.total_spent_fnb_usd || 0)} />
                <ProfileStat icon={BedDouble} label="Habitación preferida"
                             value={profile.preferred_room || '—'} />
              </div>

              {/* Preferencias dietéticas (no críticas) */}
              {profile.preferences?.dietary?.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 rounded-xl bg-forest-50 px-4 py-2.5 text-sm text-forest-700">
                  <span className="font-medium">Dieta:</span>
                  {profile.preferences.dietary.map((d) => (
                    <span key={d} className="rounded-full bg-forest-100 px-2.5 py-0.5 text-xs font-medium text-forest-600">{d}</span>
                  ))}
                </div>
              )}

              {/* Contacto */}
              <div className="rounded-2xl bg-white p-4 shadow-card">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slatey">Contacto</h3>
                <div className="space-y-1 text-sm text-ink">
                  {c.phone_number && <p className="flex items-center gap-2"><Phone size={13} className="text-slatey" />{c.phone_number}</p>}
                  {c.email && <p className="flex items-center gap-2"><Mail size={13} className="text-slatey" />{c.email}</p>}
                </div>
              </div>

              {/* Historial de estadías */}
              {profile.stays?.length > 0 && (
                <div className="rounded-2xl bg-white p-4 shadow-card">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slatey">Historial de estadías</h3>
                  <div className="space-y-2">
                    {profile.stays.map((s) => (
                      <div key={s.code} className="border-b border-mist/60 pb-2 text-sm last:border-0 last:pb-0">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-medium text-ink">
                              {s.room_type}
                              {s.room_number && <span className="ml-1.5 text-xs font-semibold tabular-nums text-hilton-600">N° {s.room_number}</span>}
                            </p>
                            <p className="text-xs text-slatey tabular-nums">
                              {formatDate(s.check_in)} → {formatDate(s.check_out)}
                            </p>
                          </div>
                          <span className="font-medium tabular-nums text-hilton-700">{formatUSD(s.total_price_usd)}</span>
                        </div>
                        {s.consumo?.length > 0 && (
                          <p className="mt-1 flex items-start gap-1 text-xs text-slatey">
                            <UtensilsCrossed size={12} className="mt-0.5 shrink-0 text-timber-400" />
                            <span>
                              {s.consumo.map((c) => `${c.qty}x ${c.name}`).join(', ')}
                              {s.consumo_total_usd ? <span className="ml-1 tabular-nums text-timber-500">· {formatUSD(s.consumo_total_usd)}</span> : null}
                            </span>
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Folio de la estadía actual (estadía + consumos del restaurante) */}
              {folio && (
                <div className="rounded-2xl bg-white p-4 shadow-card">
                  <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
                    <Receipt size={13} /> Folio · {folio.booking_code}
                  </h3>
                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between text-slatey">
                      <span>Estadía</span>
                      <span className="tabular-nums text-ink">{formatUSD(folio.summary.stay_usd)}</span>
                    </div>
                    {folio.charges?.map((ch) => (
                      <div key={ch.id} className="flex justify-between text-slatey">
                        <span className="inline-flex items-center gap-1"><UtensilsCrossed size={12} /> {ch.description}</span>
                        <span className="tabular-nums text-ink">{formatUSD(ch.amount_usd)}</span>
                      </div>
                    ))}
                    <div className="mt-1 flex justify-between border-t border-mist pt-2 font-semibold">
                      <span className="text-ink">Total a pagar</span>
                      <span className="tabular-nums text-hilton-700">{formatUSD(folio.summary.folio_total_usd)}</span>
                    </div>
                    {folio.summary.folio_pending_usd > 0 && (
                      <p className="text-xs text-amber-600">Pendiente de cobro: {formatUSD(folio.summary.folio_pending_usd)} (se salda al check-out)</p>
                    )}
                  </div>
                </div>
              )}

              {/* Conversaciones con Aura (web y WhatsApp). Cada una abre su transcripción. */}
              <div className="rounded-2xl bg-white p-4 shadow-card">
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
                  <MessageSquare size={13} /> Conversaciones con Aura
                </h3>
                {conversations.length === 0 ? (
                  <p className="text-sm text-slatey">Este huésped no tiene conversaciones registradas.</p>
                ) : (
                  <div className="space-y-2">
                    {conversations.map((cv) => {
                      const isWa = (cv.channel === 'whatsapp') || (cv.session_id || '').startsWith('wa_')
                      return (
                        <button
                          key={cv.id}
                          onClick={() => setOpenChat(cv)}
                          className="flex w-full items-center justify-between gap-2 rounded-xl border border-mist px-3 py-2 text-left transition hover:bg-mist/60"
                        >
                          <span className="flex min-w-0 items-center gap-2 text-sm">
                            <span className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${isWa ? 'bg-green-50 text-green-600' : 'bg-hilton-50 text-hilton-600'}`}>
                              {isWa ? <MessageCircle size={13} /> : <Globe size={13} />}
                            </span>
                            <span className="min-w-0">
                              <span className="block font-medium text-ink">{isWa ? 'WhatsApp' : 'Chat web'}</span>
                              <span className="block text-xs text-slatey tabular-nums">{formatDate(cv.started_at)} · {cv.message_count || 0} mensajes</span>
                            </span>
                          </span>
                          <MessageSquare size={14} className="shrink-0 text-slatey" />
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Consultas y reclamos (post-venta): cada uno abre su detalle (descripción +
                  cómo se resolvió + la conversación que lo originó). */}
              {profile.tickets?.length > 0 && (
                <div className="rounded-2xl bg-white p-4 shadow-card">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">
                    <LifeBuoy size={13} /> Consultas y reclamos
                  </h3>
                  <div className="space-y-2">
                    {profile.tickets.map((t) => {
                      const st = ticketStatusBadge(t)
                      return (
                        <button
                          key={t.id}
                          onClick={() => setSelectedTicket(t)}
                          className="flex w-full items-center justify-between gap-2 border-b border-mist/60 pb-2 text-left text-sm transition last:border-0 last:pb-0 hover:opacity-80"
                        >
                          <div className="min-w-0">
                            <p className="truncate font-medium text-ink">{t.subject}</p>
                            <p className="text-xs text-slatey tabular-nums">{t.ticket_number} · {formatDate(t.created_at)}</p>
                          </div>
                          <span className="flex shrink-0 items-center gap-1.5">
                            <Badge tone={st.tone}>{st.label}</Badge>
                            <ChevronRight size={15} className="text-slatey" />
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Editor de preferencias */}
              <div className="rounded-2xl bg-white p-4 shadow-card">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slatey">
                  Preferencias del huésped
                </h3>
                <PreferenceEditor profile={profile} onSave={save} saving={saving} />
              </div>
            </div>
          )}
        </div>

        {/* Transcripción de una conversación elegida: se monta sobre el perfil, con volver. */}
        {openChat && (
          <div className="absolute inset-0 flex flex-col bg-linen">
            <header className="flex items-center gap-2 border-b border-hilton-100 bg-white px-5 py-4">
              <button onClick={() => setOpenChat(null)} aria-label="Volver" className="rounded-lg p-1.5 text-slatey transition hover:bg-mist">
                <ChevronLeft size={18} />
              </button>
              <div className="min-w-0">
                <h2 className="truncate font-serif text-base font-700 text-ink">Conversación con Aura</h2>
                <p className="text-xs text-slatey">
                  {((openChat.channel === 'whatsapp') || (openChat.session_id || '').startsWith('wa_')) ? 'WhatsApp' : 'Chat web'} · {formatDate(openChat.started_at)}
                </p>
              </div>
            </header>
            <div className="flex-1 overflow-y-auto">
              <ChatTranscript sessionId={openChat.session_id} />
            </div>
          </div>
        )}

        {/* Detalle de una consulta/reclamo: descripción, cómo se resolvió y la conversación. */}
        {selectedTicket && (
          <TicketDetailDrawer ticket={selectedTicket} onClose={() => setSelectedTicket(null)} />
        )}
      </aside>

      {editing && (
        <EditContactModal contact={c} onClose={() => setEditing(false)} onSave={saveContact} />
      )}
    </div>
  )
}

// ── Detalle de una consulta/reclamo (solo lectura) ──────────────────────────
// Overlay sobre el perfil del huésped. Muestra el detalle del ticket y la conversación que
// lo originó. No replica la gestión operativa (eso vive en Operaciones).
function TicketDetailDrawer({ ticket, onClose }) {
  const st = ticketStatusBadge(ticket)
  return (
    <div className="absolute inset-0 flex flex-col bg-linen">
      <header className="flex items-start gap-2 border-b border-hilton-100 bg-white px-5 py-4">
        <button onClick={onClose} aria-label="Volver" className="mt-0.5 rounded-lg p-1.5 text-slatey transition hover:bg-mist">
          <ChevronLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate font-serif text-base font-700 text-ink">{ticket.subject}</h2>
          <p className="text-xs text-slatey tabular-nums">{ticket.ticket_number} · {formatDate(ticket.created_at)}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge tone={st.tone}>{st.label}</Badge>
            {ticket.category && <Badge tone="gray">{TICKET_CATEGORY_LABELS[ticket.category] || ticket.category}</Badge>}
            {ticket.assigned_area && <Badge tone="gray">{ticket.assigned_area}</Badge>}
          </div>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {ticket.description && (
          <div className="rounded-2xl bg-white p-4 shadow-card">
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slatey">Detalle</h3>
            <p className="whitespace-pre-wrap text-sm text-ink">{ticket.description}</p>
          </div>
        )}

        {ticket.resolution_note && (
          <div className="rounded-2xl bg-forest-50 p-4">
            <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-forest-700">
              <CheckCircle2 size={13} /> Cómo se resolvió
            </h3>
            <p className="whitespace-pre-wrap text-sm text-ink">{ticket.resolution_note}</p>
          </div>
        )}

        <div className="rounded-2xl bg-white shadow-card">
          <h3 className="flex items-center gap-1.5 px-4 pt-4 text-xs font-semibold uppercase tracking-wide text-slatey">
            <MessageSquare size={13} /> Conversación
          </h3>
          <ChatTranscript sessionId={ticket.session_id} />
        </div>
      </div>
    </div>
  )
}

// ── Modal de edición de datos del pasajero ──────────────────────────────────
function EditContactModal({ contact, onClose, onSave }) {
  const [firstName, setFirstName] = useState(contact.first_name || '')
  const [lastName, setLastName] = useState(contact.last_name || '')
  const [email, setEmail] = useState(contact.email || '')
  const [phone, setPhone] = useState(contact.phone_number || '')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    setSaving(true)
    try {
      await onSave({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone_number: phone.trim(),
      })
    } catch {
      setSaving(false)   // el toast de error ya lo mostró el caller
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">Editar pasajero</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={20} /></button>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <PField label="Nombre" value={firstName} onChange={setFirstName} placeholder="Nombre" />
            <PField label="Apellido" value={lastName} onChange={setLastName} placeholder="Apellido" />
          </div>
          <PField label="Email" value={email} onChange={setEmail} placeholder="email@ejemplo.com" type="email" />
          <PField label="Teléfono" value={phone} onChange={setPhone} placeholder="+54 9 11 …" />
          <p className="text-xs text-slatey">El teléfono identifica al pasajero; debe ser único.</p>
          <div className="flex justify-end gap-3 pt-1">
            <button onClick={onClose} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">Cancelar</button>
            <button onClick={submit} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60">
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function PField({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        type={type} value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
    </label>
  )
}
