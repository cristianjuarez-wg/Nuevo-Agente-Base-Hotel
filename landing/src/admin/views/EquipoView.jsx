import { useEffect, useState } from 'react'
import { Users, RefreshCw, Plus, Pencil, Trash2, X, Crown, Briefcase } from 'lucide-react'
import { listStaff, saveStaff, setStaffActive, deleteStaff } from '../../services/api'
import { PageHeader, ResponsiveTable, Badge, Loading, EmptyState, WhatsAppDot } from '../ui'
import { toast } from '../toast'

function RoleBadge({ role }) {
  return role === 'owner'
    ? <Badge tone="amber"><Crown size={11} className="mr-1" /> Dueño</Badge>
    : <Badge tone="blue"><Briefcase size={11} className="mr-1" /> Staff</Badge>
}

export default function EquipoView() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [edit, setEdit] = useState(null)        // null=cerrado, {}=nuevo, {...}=editar
  const [confirmDel, setConfirmDel] = useState(null)

  const load = () => {
    setLoading(true)
    listStaff()
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const toggle = async (m) => {
    try {
      await setStaffActive(m.id, !m.active)
      load()
      toast.success(m.active ? 'Miembro desactivado' : 'Miembro activado')
    } catch {
      toast.error('No se pudo cambiar el estado')
    }
  }

  const remove = async (m) => {
    try {
      await deleteStaff(m.id)
      setConfirmDel(null)
      load()
      toast.success(`${m.name} eliminado del equipo`)
    } catch {
      toast.error('No se pudo eliminar')
    }
  }

  const columns = [
    { key: 'name', label: 'Nombre', render: (r) => <span className="font-medium text-ink">{r.name}</span> },
    { key: 'phone', label: 'WhatsApp', render: (r) => (
      <span className="inline-flex items-center gap-1.5 tabular-nums text-slatey">
        {r.phone}<WhatsAppDot linked={r.whatsapp_linked} title="WhatsApp del equipo" />
      </span>
    ) },
    { key: 'role', label: 'Rol', render: (r) => <RoleBadge role={r.role} /> },
    { key: 'active', label: 'Estado', render: (r) => (
      <button onClick={() => toggle(r)} className="text-xs font-medium">
        {r.active
          ? <Badge tone="green">Activo</Badge>
          : <Badge tone="gray">Inactivo</Badge>}
      </button>
    ) },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex items-center gap-1">
        <button onClick={() => setEdit(r)} title="Editar" className="rounded-lg p-2 text-slatey transition hover:bg-mist hover:text-ink"><Pencil size={15} /></button>
        <button onClick={() => setConfirmDel(r)} title="Eliminar" className="rounded-lg p-2 text-slatey transition hover:bg-red-50 hover:text-red-600"><Trash2 size={15} /></button>
      </div>
    ) },
  ]

  const renderCard = (r) => (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-ink">{r.name}</span>
        <RoleBadge role={r.role} />
      </div>
      <p className="flex items-center gap-1.5 text-xs tabular-nums text-slatey">{r.phone}<WhatsAppDot linked={r.whatsapp_linked} title="WhatsApp del equipo" /></p>
      <div className="mt-2 flex items-center justify-between">
        <button onClick={() => toggle(r)}>
          {r.active ? <Badge tone="green">Activo</Badge> : <Badge tone="gray">Inactivo</Badge>}
        </button>
        <div className="flex gap-1">
          <button onClick={() => setEdit(r)} className="rounded-lg p-2 text-slatey hover:bg-mist"><Pencil size={15} /></button>
          <button onClick={() => setConfirmDel(r)} className="rounded-lg p-2 text-slatey hover:bg-red-50 hover:text-red-600"><Trash2 size={15} /></button>
        </div>
      </div>
    </div>
  )

  return (
    <div>
      <PageHeader
        title="Equipo"
        subtitle="Personal y dueño del hotel. El agente de WhatsApp reconoce su número y los atiende según su rol (el dueño accede a las métricas del negocio)."
        right={
          <div className="flex items-center gap-2">
            <button onClick={load} className="btn-secondary px-4 py-2 text-xs"><RefreshCw size={14} /> Actualizar</button>
            <button onClick={() => setEdit({})} className="btn-primary px-4 py-2 text-xs"><Plus size={14} /> Agregar</button>
          </div>
        }
      />
      {loading ? (
        <Loading />
      ) : rows.length === 0 ? (
        <EmptyState icon={Users} title="Aún no hay miembros del equipo"
                    desc="Agregá al dueño y al personal con su número de WhatsApp para que el agente los reconozca." />
      ) : (
        <ResponsiveTable columns={columns} rows={rows.map((r) => ({ ...r, _key: r.id }))} renderCard={renderCard} />
      )}

      {edit && <StaffModal member={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load() }} />}
      {confirmDel && (
        <Modal title={`Eliminar a ${confirmDel.name}`} icon={Trash2} onClose={() => setConfirmDel(null)}>
          <p className="text-sm text-slatey">¿Seguro que querés eliminar a este miembro del equipo? Esta acción no se puede deshacer.</p>
          <div className="mt-5 flex justify-end gap-2">
            <button onClick={() => setConfirmDel(null)} className="btn-secondary px-4 py-2 text-sm">Cancelar</button>
            <button onClick={() => remove(confirmDel)} className="rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700">Eliminar</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function StaffModal({ member, onClose, onSaved }) {
  const isNew = !member.id
  const [name, setName] = useState(member.name || '')
  const [phone, setPhone] = useState(member.phone || '')
  const [role, setRole] = useState(member.role || 'staff')
  const [active, setActive] = useState(member.active ?? true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    if (!name.trim()) { setError('El nombre es obligatorio.'); return }
    if (!phone.trim()) { setError('El teléfono de WhatsApp es obligatorio.'); return }
    setSaving(true)
    setError('')
    try {
      await saveStaff({ name: name.trim(), phone: phone.trim(), role, active }, member.id)
      toast.success(isNew ? 'Miembro agregado' : 'Miembro actualizado')
      onSaved()
    } catch (e) {
      // El backend manda el motivo en `detail` (HTTPException) o `message` (handler global).
      const data = e?.response?.data || {}
      const msg = data.detail || data.message || 'No se pudo guardar. Verificá el teléfono.'
      setError(msg)
      setSaving(false)
    }
  }

  return (
    <Modal title={isNew ? 'Agregar al equipo' : 'Editar miembro'} icon={Users} onClose={onClose}>
      <div className="space-y-4">
        <Field label="Nombre *" value={name} onChange={setName} placeholder="Ej: María García" />
        <Field label="WhatsApp *" value={phone} onChange={setPhone} placeholder="Ej: +54 9 11 1234 5678" />
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Rol</span>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100">
            <option value="staff">Staff (personal)</option>
            <option value="owner">Dueño / Gerente (acceso a métricas)</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="h-4 w-4 rounded border-hilton-300" />
          Activo
        </label>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <button onClick={save} disabled={saving} className="btn-primary w-full py-2.5 text-sm disabled:opacity-60">
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  )
}

function Modal({ title, icon: Icon, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            {Icon && <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-hilton-50 text-hilton-600"><Icon size={18} /></div>}
            <h3 className="font-serif text-lg font-700 text-ink">{title}</h3>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist"><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        type="text" value={value || ''} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 px-3.5 py-2.5 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
    </label>
  )
}
