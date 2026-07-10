import { useState, useEffect } from 'react'
import { Lock, LogIn } from 'lucide-react'
import { login, isAuthenticated } from '../services/api'
import { toast } from './toast'

/**
 * Gate de autenticación del backoffice (Fase 2.5). Si no hay sesión, muestra el login;
 * si la hay, renderiza `children` (el AdminApp). Escucha 'auth:unauthorized' (que emite
 * el interceptor de api.js en un 401) para volver al login cuando la sesión expira.
 */
export default function LoginGate({ children }) {
  const [authed, setAuthed] = useState(isAuthenticated())

  useEffect(() => {
    const onUnauth = () => setAuthed(false)
    window.addEventListener('auth:unauthorized', onUnauth)
    return () => window.removeEventListener('auth:unauthorized', onUnauth)
  }, [])

  if (authed) return children
  return <LoginScreen onSuccess={() => setAuthed(true)} />
}

function LoginScreen({ onSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!email.trim() || !password) return
    setLoading(true)
    try {
      const user = await login(email.trim(), password)
      toast.success(`Bienvenido, ${user.email}`)
      onSuccess()
    } catch (err) {
      const msg = err?.response?.data?.detail || 'No se pudo iniciar sesión.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const inputCls =
    'w-full rounded-xl border border-hilton-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-hilton-100'

  return (
    <div className="flex min-h-screen items-center justify-center bg-mist px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-7 shadow-card">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-hilton-600 text-white">
            <Lock size={24} />
          </div>
          <h1 className="font-serif text-xl font-700 text-ink">Backoffice</h1>
          <p className="text-sm text-slatey">Iniciá sesión para continuar.</p>
        </div>

        <label className="mb-1 block text-sm font-medium text-ink">Email</label>
        <input
          type="email" value={email} onChange={(e) => setEmail(e.target.value)}
          autoComplete="username" className={inputCls + ' mb-4'} placeholder="tu@hotel.com"
        />

        <label className="mb-1 block text-sm font-medium text-ink">Contraseña</label>
        <input
          type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" className={inputCls + ' mb-6'} placeholder="••••••••"
        />

        <button
          type="submit" disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-hilton-700 disabled:opacity-60"
        >
          <LogIn size={16} /> {loading ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </div>
  )
}
