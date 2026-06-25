import { useState, useEffect } from 'react'
import { Database, Sparkles, Trash2, Loader2, X, AlertTriangle, Info, ShieldAlert } from 'lucide-react'
import { getDemoStatus, populateDemo, clearDemo, resetAllData } from '../../../services/api'
import { PageHeader, Loading } from '../../ui'
import { toast } from '../../toast'
import { useAdminGate } from '../../components/useAdminGate'

const ENTITY_LABELS = {
  contacts: 'Pasajeros',
  bookings: 'Reservas',
  leads: 'Leads',
  conversations: 'Conversaciones',
  messages: 'Mensajes',
  tickets: 'Tickets de soporte',
  staff: 'Equipo',
}

function summary(counts) {
  return Object.entries(ENTITY_LABELS)
    .filter(([k]) => counts?.[k])
    .map(([k, label]) => `${counts[k]} ${label.toLowerCase()}`)
    .join(', ')
}

export default function DemoView() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')        // 'populate' | 'clear' | 'reset' | ''
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetWord, setResetWord] = useState('')
  const { runProtected, gateModal } = useAdminGate()

  const load = () => {
    setLoading(true)
    getDemoStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const handlePopulate = async () => {
    setWorking('populate')
    try {
      await runProtected(async () => {
        const res = await populateDemo()
        setStatus(await getDemoStatus())
        toast.success(`Demo generada: ${summary(res.created)}`)
      })
    } catch {
      toast.error('No se pudo generar la demo. Intentá de nuevo.')
    } finally {
      setWorking('')
    }
  }

  const handleClear = async () => {
    setWorking('clear')
    setConfirmClear(false)
    try {
      await runProtected(async () => {
        await clearDemo()
        setStatus(await getDemoStatus())
        toast.success('Datos de demostración eliminados.')
      })
    } catch {
      toast.error('No se pudo limpiar la demo. Intentá de nuevo.')
    } finally {
      setWorking('')
    }
  }

  const handleResetAll = async () => {
    setWorking('reset')
    try {
      await runProtected(async () => {
        const res = await resetAllData('RESETEAR')
        setStatus(await getDemoStatus())
        setConfirmReset(false)
        setResetWord('')
        toast.success(`Base reseteada: ${res.total} registros borrados.`)
      })
    } catch (e) {
      const msg = e?.response?.data?.detail || 'No se pudo resetear. Intentá de nuevo.'
      toast.error(msg)
    } finally {
      setWorking('')
    }
  }

  if (loading) return <Loading label="Cargando estado de la demo…" />

  const hasData = status?.has_data
  const busy = !!working

  return (
    <div>
      {gateModal}
      <PageHeader
        title="Datos de demostración"
        subtitle="Poblá el backoffice con pasajeros, reservas, leads, conversaciones y tickets de ejemplo para mostrar la plataforma en acción."
      />

      {/* Aviso de alcance */}
      <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-hilton-100 bg-hilton-50 px-4 py-3 text-sm text-hilton-700">
        <Info size={16} className="mt-0.5 shrink-0" />
        <span>
          Solo afecta a los <strong>datos de demostración</strong>. Tus reservas reales de prueba y la
          configuración (habitaciones, promociones, temas, conocimiento) <strong>no se tocan</strong>.
        </span>
      </div>

      {/* Estado actual */}
      <div className="mb-5 rounded-2xl bg-white p-5 shadow-card">
        <div className="mb-4 flex items-center gap-2">
          <Database size={18} className="text-hilton-600" />
          <h2 className="font-serif text-lg font-600 text-ink">Estado actual</h2>
        </div>
        {hasData ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(ENTITY_LABELS).map(([k, label]) => (
              <div key={k} className="rounded-xl bg-mist/60 p-3 text-center">
                <p className="font-serif text-2xl font-700 tabular-nums text-ink">{status[k] ?? 0}</p>
                <p className="text-xs text-slatey">{label}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slatey">No hay datos de demostración cargados en este momento.</p>
        )}
      </div>

      {/* Acciones */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          onClick={handlePopulate}
          disabled={busy}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-hilton-600 px-5 py-3 text-sm font-medium text-white shadow-card transition hover:bg-hilton-700 disabled:opacity-60"
        >
          {working === 'populate' ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          {working === 'populate'
            ? 'Generando…'
            : hasData ? 'Regenerar demo' : 'Poblar demo'}
        </button>

        {hasData && (
          <button
            onClick={() => setConfirmClear(true)}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 px-5 py-3 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
          >
            {working === 'clear' ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
            Limpiar datos demo
          </button>
        )}
      </div>

      {hasData && (
        <p className="mt-3 text-xs text-slatey">
          «Regenerar» borra la demo actual y crea una nueva con fechas actualizadas a hoy.
        </p>
      )}

      {/* Zona de peligro: resetear TODO (real + demo) */}
      <div className="mt-10 rounded-2xl border border-red-200 bg-red-50/50 p-5">
        <div className="mb-2 flex items-center gap-2">
          <ShieldAlert size={18} className="text-red-600" />
          <h2 className="font-serif text-lg font-600 text-red-700">Zona de peligro</h2>
        </div>
        <p className="mb-1 text-sm text-ink">
          <strong>Resetear todo</strong> borra todas las reservas, huéspedes, leads, conversaciones,
          tickets y pedidos/reservas del restaurante — <strong>reales y de demostración</strong>.
        </p>
        <p className="mb-4 text-xs text-slatey">
          Conserva la configuración: habitaciones, <strong>carta del restaurante</strong>, base de
          conocimiento, comercios amigos, promociones y temas. Esta acción no se puede deshacer.
        </p>
        <button
          onClick={() => { setResetWord(''); setConfirmReset(true) }}
          disabled={busy}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-5 py-3 text-sm font-medium text-white shadow-card transition hover:bg-red-700 disabled:opacity-60"
        >
          {working === 'reset' ? <Loader2 size={16} className="animate-spin" /> : <ShieldAlert size={16} />}
          Resetear todo
        </button>
      </div>

      {/* Confirmación de reset total: exige tipear RESETEAR */}
      {confirmReset && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setConfirmReset(false)} />
          <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 text-red-600">
                  <ShieldAlert size={18} />
                </div>
                <h3 className="font-serif text-lg font-700 text-ink">Resetear todo</h3>
              </div>
              <button onClick={() => setConfirmReset(false)} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
                <X size={20} />
              </button>
            </div>
            <p className="mb-3 text-sm text-ink">
              Vas a borrar <strong>TODOS</strong> los datos generados (reales y de demo): reservas,
              huéspedes, leads, conversaciones, tickets y pedidos del restaurante. La configuración
              y la carta se conservan.
            </p>
            <p className="mb-2 text-xs font-medium text-red-600">Esta acción es irreversible.</p>
            <label className="mb-1 block text-xs font-medium text-ink">
              Para confirmar, tipeá <span className="font-mono font-bold">RESETEAR</span>:
            </label>
            <input
              value={resetWord}
              onChange={(e) => setResetWord(e.target.value)}
              placeholder="RESETEAR"
              className="mb-5 w-full rounded-xl border border-red-200 px-3.5 py-2.5 text-sm focus:border-red-400 focus:outline-none focus:ring-2 focus:ring-red-100"
            />
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmReset(false)} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">
                Cancelar
              </button>
              <button
                onClick={handleResetAll}
                disabled={resetWord !== 'RESETEAR' || working === 'reset'}
                className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
              >
                {working === 'reset' ? <Loader2 size={15} className="animate-spin" /> : <ShieldAlert size={15} />} Sí, resetear todo
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmación de limpieza */}
      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setConfirmClear(false)} />
          <div className="relative w-full max-w-md rounded-t-3xl bg-white p-6 shadow-card-lg animate-slide-up sm:rounded-3xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 text-red-600">
                  <AlertTriangle size={18} />
                </div>
                <h3 className="font-serif text-lg font-700 text-ink">Limpiar datos demo</h3>
              </div>
              <button onClick={() => setConfirmClear(false)} aria-label="Cerrar" className="rounded-lg p-1.5 text-slatey hover:bg-mist">
                <X size={20} />
              </button>
            </div>
            <p className="mb-2 text-sm text-slatey">Vas a eliminar:</p>
            <ul className="mb-4 space-y-1 text-sm text-ink">
              {Object.entries(ENTITY_LABELS).filter(([k]) => status?.[k]).map(([k, label]) => (
                <li key={k} className="flex justify-between">
                  <span>{label}</span>
                  <span className="font-semibold tabular-nums">{status[k]}</span>
                </li>
              ))}
            </ul>
            <p className="mb-5 text-xs text-slatey">Esta acción no se puede deshacer. Solo se borran los datos demo.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmClear(false)} className="rounded-xl border border-hilton-200 px-4 py-2.5 text-sm text-slatey transition hover:bg-mist">
                Cancelar
              </button>
              <button onClick={handleClear} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700">
                <Trash2 size={15} /> Sí, limpiar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
