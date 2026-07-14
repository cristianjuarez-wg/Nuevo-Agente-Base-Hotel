import { useState, useEffect } from 'react'
import { Building2, MapPin, Coins, Pencil, X, Plus, Trash2, Phone, Mail, UtensilsCrossed } from 'lucide-react'
import { getBusinessProfile, updateBusinessProfile } from '../../../services/api'
import { Badge } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

// Etiqueta legible del dialecto (afecta cómo habla el agente).
const DIALECT_LABEL = {
  rioplatense_voseo: 'Rioplatense (voseo)',
  es_neutro: 'Español neutro',
  es_tuteo: 'Español (tuteo)',
  en: 'Inglés',
}
const DIALECT_OPTIONS = Object.keys(DIALECT_LABEL)

export default function BusinessIdentityView() {
  const { runProtected, gateModal } = useAdminGate()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    getBusinessProfile()
      .then(setProfile)
      .catch(() => toast.error('No se pudo cargar la identidad del negocio'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-sm text-slatey">Cargando…</div>
  if (!profile) return <div className="p-6 text-sm text-slatey">Sin datos.</div>

  const initial = (profile.business_name || '?').trim().charAt(0).toUpperCase()
  const money = profile.secondary_currency
    ? `${profile.primary_currency} / ${profile.secondary_currency}`
    : profile.primary_currency

  return (
    <div>
      {gateModal}

      {/* Ficha de identidad del negocio */}
      <div className="rounded-2xl bg-white p-5 shadow-card sm:p-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-hilton-600 font-serif text-2xl font-700 text-white">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-serif text-xl font-700 text-ink">{profile.business_name}</h2>
              <Badge tone="blue">{DIALECT_LABEL[profile.dialect_style] || profile.dialect_style}</Badge>
              <Badge tone="amber">{money}</Badge>
            </div>
            {profile.brand_line && <p className="mt-1 text-sm text-slatey">{profile.brand_line}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slatey">
              <span className="inline-flex items-center gap-1.5">
                <Building2 size={13} /> Agente: {profile.agent_display_name} ({profile.role_descriptor})
              </span>
              <span className="inline-flex items-center gap-1.5">
                <MapPin size={13} /> {profile.city || '—'}{profile.region_line ? ` · ${profile.region_line}` : ''} · {profile.timezone}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Coins size={13} /> {profile.language}
              </span>
              {profile.restaurant_name && (
                <span className="inline-flex items-center gap-1.5">
                  <UtensilsCrossed size={13} /> {profile.restaurant_name}
                </span>
              )}
            </div>
            {/* Contacto que el agente da a los huéspedes ("contactanos al…"). */}
            {(profile.contact_phone || profile.contact_email) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-slatey">
                {profile.contact_phone && (
                  <span className="inline-flex items-center gap-1.5"><Phone size={13} /> {profile.contact_phone}</span>
                )}
                {profile.contact_email && (
                  <span className="inline-flex items-center gap-1.5"><Mail size={13} /> {profile.contact_email}</span>
                )}
              </div>
            )}
          </div>

          <button
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-hilton-50 px-3 py-2 text-sm font-medium text-hilton-700 hover:bg-hilton-100"
          >
            <Pencil size={15} /> Editar
          </button>
        </div>

        {/* Hechos del negocio */}
        <div className="mt-5 border-t border-hilton-100 pt-4">
          <p className="mb-2 text-sm font-medium text-ink">Hechos del negocio</p>
          {(profile.facts || []).length === 0 ? (
            <p className="text-sm text-slatey">
              Sin hechos cargados. Agregá datos que el agente NO debe inventar ni contradecir
              (ej. “No tiene spa”, “Desayuno incluido”).
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {profile.facts.map((f, i) => (
                <li key={i} className="text-sm text-slatey">• {f}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="mt-3 text-xs text-slatey">
        Esta identidad se inyecta en todos los agentes. Cambiar el nombre, el dialecto o la
        moneda acá cambia cómo se presenta y responde el agente, sin tocar código.
      </p>

      {editing && (
        <EditProfileModal
          profile={profile}
          onClose={() => setEditing(false)}
          onSave={(payload) =>
            runProtected(async () => {
              const updated = await updateBusinessProfile(payload)
              setProfile(updated)
              setEditing(false)
              toast.success('Identidad del negocio actualizada')
            })
          }
        />
      )}
    </div>
  )
}

function EditProfileModal({ profile, onClose, onSave }) {
  const [f, setF] = useState({
    business_name: profile.business_name || '',
    brand_line: profile.brand_line || '',
    agent_display_name: profile.agent_display_name || '',
    role_descriptor: profile.role_descriptor || '',
    restaurant_name: profile.restaurant_name || '',
    contact_phone: profile.contact_phone || '',
    contact_email: profile.contact_email || '',
    city: profile.city || '',
    region_line: profile.region_line || '',
    timezone: profile.timezone || '',
    language: profile.language || 'es',
    dialect_style: profile.dialect_style || 'rioplatense_voseo',
    primary_currency: profile.primary_currency || 'USD',
    secondary_currency: profile.secondary_currency || '',
    facts: [...(profile.facts || [])],
  })

  const set = (k, v) => setF((prev) => ({ ...prev, [k]: v }))
  const setFact = (i, v) => setF((prev) => ({ ...prev, facts: prev.facts.map((x, j) => (j === i ? v : x)) }))
  const addFact = () => setF((prev) => ({ ...prev, facts: [...prev.facts, ''] }))
  const delFact = (i) => setF((prev) => ({ ...prev, facts: prev.facts.filter((_, j) => j !== i) }))

  const inputCls =
    'w-full rounded-xl border border-hilton-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100'
  const labelCls = 'mb-1 block text-sm font-medium text-ink'

  const save = () => {
    // secondary_currency vacío → null (monomoneda). facts sin vacíos.
    onSave({
      ...f,
      business_name: f.business_name.trim(),
      secondary_currency: f.secondary_currency.trim() || null,
      facts: f.facts.map((x) => x.trim()).filter(Boolean),
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <header className="mb-5 flex items-center justify-between">
          <h3 className="font-serif text-lg font-700 text-ink">Editar identidad del negocio</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
            <X size={20} />
          </button>
        </header>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={labelCls}>Nombre del negocio</label>
            <input value={f.business_name} onChange={(e) => set('business_name', e.target.value)} className={inputCls} />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls}>Tagline / línea de marca</label>
            <input value={f.brand_line} onChange={(e) => set('brand_line', e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Nombre del agente</label>
            <input value={f.agent_display_name} onChange={(e) => set('agent_display_name', e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Rol del agente</label>
            <input value={f.role_descriptor} onChange={(e) => set('role_descriptor', e.target.value)} className={inputCls} placeholder="concierge, asistente…" />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls}>Nombre del restaurante</label>
            <input value={f.restaurant_name} onChange={(e) => set('restaurant_name', e.target.value)} className={inputCls} placeholder="ej. Plaza — Hampton's Kitchen House" />
          </div>
          <div>
            <label className={labelCls}>Teléfono de contacto</label>
            <input value={f.contact_phone} onChange={(e) => set('contact_phone', e.target.value)} className={inputCls} placeholder="+54 294-474-6200" />
          </div>
          <div>
            <label className={labelCls}>Email de contacto</label>
            <input type="email" value={f.contact_email} onChange={(e) => set('contact_email', e.target.value)} className={inputCls} placeholder="info@hotel.com" />
          </div>
          <div>
            <label className={labelCls}>Ciudad</label>
            <input value={f.city} onChange={(e) => set('city', e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Zona horaria (IANA)</label>
            <input value={f.timezone} onChange={(e) => set('timezone', e.target.value)} className={inputCls} placeholder="America/Argentina/Buenos_Aires" />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls}>Color local (región)</label>
            <input value={f.region_line} onChange={(e) => set('region_line', e.target.value)} className={inputCls} placeholder="frente al Caribe, en plena Patagonia…" />
          </div>
          <div>
            <label className={labelCls}>Dialecto</label>
            <select value={f.dialect_style} onChange={(e) => set('dialect_style', e.target.value)} className={inputCls}>
              {DIALECT_OPTIONS.map((d) => (
                <option key={d} value={d}>{DIALECT_LABEL[d]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>Idioma (código)</label>
            <input value={f.language} onChange={(e) => set('language', e.target.value)} className={inputCls} placeholder="es, en, pt…" />
          </div>
          <div>
            <label className={labelCls}>Moneda principal</label>
            <input value={f.primary_currency} onChange={(e) => set('primary_currency', e.target.value.toUpperCase())} className={inputCls} placeholder="USD, MXN…" />
          </div>
          <div>
            <label className={labelCls}>Moneda secundaria (opcional)</label>
            <input value={f.secondary_currency} onChange={(e) => set('secondary_currency', e.target.value.toUpperCase())} className={inputCls} placeholder="ARS (vacío = monomoneda)" />
          </div>
        </div>

        {/* Hechos del negocio (lista editable) */}
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between">
            <label className={labelCls + ' mb-0'}>Hechos del negocio</label>
            <button onClick={addFact} className="inline-flex items-center gap-1 rounded-lg bg-hilton-50 px-2.5 py-1 text-xs font-medium text-hilton-700 hover:bg-hilton-100">
              <Plus size={13} /> Agregar
            </button>
          </div>
          {f.facts.length === 0 && <p className="text-xs text-slatey">Datos que el agente no debe inventar ni contradecir.</p>}
          <div className="flex flex-col gap-2">
            {f.facts.map((fact, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={fact} onChange={(e) => setFact(i, e.target.value)} className={inputCls} placeholder="ej. No tiene spa ni sauna" />
                <button onClick={() => delFact(i)} aria-label="Quitar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist">
            Cancelar
          </button>
          <button onClick={save} className="rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700">
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}
