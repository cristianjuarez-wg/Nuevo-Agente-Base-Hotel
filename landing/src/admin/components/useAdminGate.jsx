import { useState, useCallback } from 'react'
import AdminKeyModal from './AdminKeyModal'
import { clearAdminKey } from '../../services/api'

/**
 * Hook para proteger acciones críticas del backoffice con la clave de administración.
 *
 * Uso:
 *   const { runProtected, gateModal } = useAdminGate()
 *   ...
 *   onClick={() => runProtected(async () => { await updateUsageConfig(payload) ; toast... })}
 *   ...
 *   return (<div>...{gateModal}</div>)
 *
 * Cómo funciona:
 *   - runProtected(action) ejecuta `action()`.
 *   - Si el backend responde 403 (clave faltante o incorrecta), borra la clave guardada,
 *     abre el modal pidiéndola y, al confirmar, reintenta `action()` automáticamente.
 *   - Si no hay ADMIN_KEY configurada en el backend, la acción pasa directo (no hay 403).
 */
export function useAdminGate() {
  const [pending, setPending] = useState(null)   // la acción a reintentar
  const [error, setError] = useState('')

  const runProtected = useCallback(async (action) => {
    try {
      await action()
    } catch (e) {
      if (e?.response?.status === 403) {
        clearAdminKey()
        setError(error ? 'Clave incorrecta. Probá de nuevo.' : '')
        setPending(() => action)   // guardamos la acción para reintentar tras ingresar la clave
      } else {
        throw e   // otros errores los maneja el caller
      }
    }
  }, [error])

  const onConfirm = useCallback(async () => {
    const action = pending
    if (!action) return
    try {
      await action()
      setPending(null)
      setError('')
    } catch (e) {
      if (e?.response?.status === 403) {
        clearAdminKey()
        setError('Clave incorrecta. Probá de nuevo.')
      } else {
        setPending(null)
        setError('')
        throw e
      }
    }
  }, [pending])

  const gateModal = pending ? (
    <AdminKeyModal
      error={error}
      onConfirm={onConfirm}
      onClose={() => { setPending(null); setError('') }}
    />
  ) : null

  return { runProtected, gateModal }
}
