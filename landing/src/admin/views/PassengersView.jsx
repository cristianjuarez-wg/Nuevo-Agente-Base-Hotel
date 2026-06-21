import { useEffect, useState } from 'react'
import {
  Users, RefreshCw, Mail, Phone, X, BedDouble, CalendarCheck,
  Repeat, DollarSign, Star, Loader2, Trash2,
} from 'lucide-react'
import { listPassengers, getGuestProfile, updateGuestPreferences, deleteContact } from '../../services/api'
import {
  PageHeader, ResponsiveTable, Badge, OriginBadge, Loading, EmptyState, formatDate, formatUSD, WhatsAppDot,
} from '../ui'
import { toast } from '../toast'

function flatten(c) {
  const m = c.metrics || {}
  return {
    _key: c.id,
    id: c.id,
    name: c.full_name || [c.first_name, c.last_name].filter(Boolean).join(' ') || 'Sin nombre',
    email: c.email,
    phone: c.phone_number,
    whatsappLinked: c.whatsapp_linked,
    origin: c.origin,
    stays: m.purchases_made ?? 0,
    inHouse: !!c.is_staying_now,
    last: c.last_interaction_date,
  }
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
  const [dietary, setDietary] = useState((prefs.dietary || []).join(', '))
  const [services, setServices] = useState((prefs.services_used || []).join(', '))
  const [notes, setNotes] = useState(prefs.notes || '')

  const toList = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

  return (
    <div className="space-y-3">
      <Field label="Preferencias gastronómicas" hint="separadas por coma">
        <input className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none"
               value={dietary} onChange={(e) => setDietary(e.target.value)}
               placeholder="vegetariano, sin gluten" />
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
        onClick={() => onSave({ ...prefs, dietary: toList(dietary), services_used: toList(services), notes })}
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

function DetailDrawer({ contactId, onClose }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getGuestProfile(contactId).then(setProfile).catch(() => setProfile(null)).finally(() => setLoading(false))
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
          <button onClick={onClose} aria-label="Cerrar"
                  className="flex h-10 w-10 items-center justify-center rounded-lg text-slatey hover:bg-mist">
            <X size={20} />
          </button>
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

              <div className="grid grid-cols-2 gap-3">
                <ProfileStat icon={CalendarCheck} label="Estadías" value={profile.stays_count} />
                <ProfileStat icon={DollarSign} label="Gasto total"
                             value={formatUSD(profile.total_spent_usd || 0)} />
                <ProfileStat icon={BedDouble} label="Habitación preferida"
                             value={profile.preferred_room || '—'} />
                <ProfileStat icon={Repeat} label="Recurrente"
                             value={profile.is_recurring ? 'Sí' : 'No'} />
              </div>

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
                      <div key={s.code} className="flex items-center justify-between border-b border-mist/60 pb-2 text-sm last:border-0 last:pb-0">
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
                    ))}
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
      </aside>
    </div>
  )
}

// Lee un contact_id del hash "#admin/pasajeros/{id}" (deep-link desde Reservas).
function contactIdFromHash() {
  const parts = window.location.hash.replace('#admin/', '').split('/')
  const id = parts[1] ? parseInt(parts[1], 10) : null
  return Number.isInteger(id) ? id : null
}

export default function PassengersView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(contactIdFromHash)
  const [onlyInHouse, setOnlyInHouse] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const load = () => {
    setLoading(true)
    listPassengers()
      .then((d) => setRows((Array.isArray(d) ? d : []).map(flatten)))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handleDelete = async (r) => {
    if (!window.confirm(`¿Eliminar a ${r.name}? Se quitará del listado de pasajeros (sus reservas quedan, pero sin vincular). Esta acción no se puede deshacer.`)) return
    setDeletingId(r.id)
    try {
      await deleteContact(r.id)
      setRows((prev) => prev.filter((x) => x.id !== r.id))
      toast.success(`${r.name} eliminado`)
    } catch {
      toast.error('No se pudo eliminar el pasajero. Intentá de nuevo.')
    } finally {
      setDeletingId(null)
    }
  }

  const DeleteButton = ({ r }) => (
    <button
      onClick={(e) => { e.stopPropagation(); handleDelete(r) }}
      disabled={deletingId === r.id}
      title="Eliminar pasajero"
      className="inline-flex items-center justify-center rounded-lg p-1.5 text-slatey transition hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
    >
      <Trash2 size={15} />
    </button>
  )

  // Soporta deep-link: si el hash trae un contact_id, abre su drawer.
  useEffect(() => {
    const onHash = () => setSelected(contactIdFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const closeDrawer = () => {
    setSelected(null)
    // Limpia el id del hash para no reabrir al volver.
    if (window.location.hash.startsWith('#admin/pasajeros/')) window.location.hash = 'admin/pasajeros'
  }

  const columns = [
    { key: 'name', label: 'Huésped', render: (r) => (
      <div className="flex items-center gap-2">
        <button onClick={() => setSelected(r.id)} className="font-medium text-hilton-700 hover:underline">{r.name}</button>
        {r.inHouse && <Badge tone="green"><BedDouble size={11} className="mr-1" /> En casa</Badge>}
      </div>
    ) },
    { key: 'contact', label: 'Contacto', render: (r) => (
      <div className="space-y-0.5 text-xs text-slatey">
        {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} /></p>}
        {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        {!r.phone && !r.email && '—'}
      </div>
    ) },
    { key: 'origin', label: 'Origen', render: (r) => <OriginBadge origin={r.origin} /> },
    { key: 'stays', label: 'Estadías', render: (r) => <span className="tabular-nums font-medium text-ink">{r.stays}</span> },
    { key: 'last', label: 'Última actividad', render: (r) => formatDate(r.last) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center justify-end gap-1.5">
        <button onClick={() => setSelected(r.id)} className="text-xs font-medium text-hilton-600 hover:underline">Ver 360°</button>
        <DeleteButton r={r} />
      </div>
    ) },
  ]

  const renderCard = (r) => (
    <div className="relative">
      <button onClick={() => setSelected(r.id)} className="w-full text-left">
        <div className="mb-2 flex items-center justify-between pr-9">
          <span className="font-medium text-ink">{r.name}</span>
          <OriginBadge origin={r.origin} />
        </div>
        <div className="space-y-0.5 text-xs text-slatey">
          {r.phone && <p className="flex items-center gap-1"><Phone size={12} />{r.phone}<WhatsAppDot linked={r.whatsappLinked} /></p>}
          {r.email && <p className="flex items-center gap-1"><Mail size={12} />{r.email}</p>}
        </div>
        <p className="mt-2 text-xs text-slatey">
          <span className="tabular-nums font-medium text-ink">{r.stays}</span> estadía{r.stays === 1 ? '' : 's'}
        </p>
      </button>
      <div className="absolute right-0 top-0"><DeleteButton r={r} /></div>
    </div>
  )

  const inHouseCount = rows.filter((r) => r.inHouse).length
  const visible = onlyInHouse ? rows.filter((r) => r.inHouse) : rows

  return (
    <div>
      <PageHeader
        title="Pasajeros"
        subtitle="Huéspedes que reservaron al menos una vez. Tocá un nombre para ver su perfil 360°."
        right={
          <button onClick={load} className="btn-secondary px-4 py-2 text-xs">
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={Users} title="Aún no hay pasajeros"
                    desc="Cuando un huésped concrete una reserva, aparecerá acá con su historial." />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={() => setOnlyInHouse(false)}
              className={`rounded-full px-3.5 py-2 text-xs font-medium transition ${
                !onlyInHouse ? 'bg-hilton-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
              }`}
            >
              Todos <span className="tabular-nums opacity-70">({rows.length})</span>
            </button>
            <button
              onClick={() => setOnlyInHouse(true)}
              className={`flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-medium transition ${
                onlyInHouse ? 'bg-green-600 text-white shadow-card' : 'bg-white text-slatey hover:bg-hilton-50'
              }`}
            >
              <BedDouble size={13} /> Alojados ahora <span className="tabular-nums opacity-70">({inHouseCount})</span>
            </button>
          </div>
          {visible.length === 0 ? (
            <EmptyState icon={BedDouble} title="Nadie alojado ahora"
                        desc="No hay huéspedes en casa en este momento." />
          ) : (
            <ResponsiveTable columns={columns} rows={visible} renderCard={renderCard} />
          )}
        </>
      )}

      {selected && <DetailDrawer contactId={selected} onClose={closeDrawer} />}
    </div>
  )
}
