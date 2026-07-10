import { useState } from 'react'
import {
  Building2, Hotel, BookOpen, Sparkles, MessageCircle, Check, ArrowLeft, ArrowRight,
} from 'lucide-react'
import BusinessIdentityView from './BusinessIdentityView'
import HabitacionesView from '../HabitacionesView'
import KnowledgeView from '../agente/KnowledgeView'
import EmployeeHubSection from '../centro/EmployeeHubSection'

/**
 * Wizard de configuración inicial (Fase 3.2). NO trae features nuevas: ORQUESTA las vistas que
 * ya existen (identidad, catálogo, conocimiento, entrenamiento) en un flujo guiado de 5 pasos
 * para dar de alta un cliente nuevo desde el backoffice. El último paso es una prueba (chat
 * embebido + checklist). Cada paso reusa su vista tal cual — se puede seguir editando después
 * desde las secciones normales; el wizard es solo el camino de primera configuración.
 */
const STEPS = [
  { id: 'identidad', label: 'Identidad', icon: Building2,
    help: 'Nombre del negocio, agente, idioma, moneda y hechos. Es la base de todo lo que dice el agente.' },
  { id: 'catalogo', label: 'Catálogo', icon: Hotel,
    help: 'Las habitaciones y sus precios. El agente ofrece disponibilidad y reserva a partir de acá.' },
  { id: 'conocimiento', label: 'Conocimiento', icon: BookOpen,
    help: 'Documentos del hotel (servicios, políticas, pagos, lugares). El agente los usa por RAG.' },
  { id: 'tono', label: 'Tono y política', icon: Sparkles,
    help: 'Cómo habla y qué política comercial sigue el agente (entrenamiento). Opcional: hay defaults.' },
  { id: 'prueba', label: 'Prueba', icon: MessageCircle,
    help: 'Probá el agente antes de salir a producción con el checklist de go-live.' },
]

export default function OnboardingWizard() {
  const [step, setStep] = useState(0)
  const current = STEPS[step]

  return (
    <div>
      {/* Encabezado + progreso */}
      <div className="mb-5">
        <h1 className="font-serif text-xl font-700 text-ink">Configuración inicial</h1>
        <p className="mt-1 text-sm text-slatey">
          Guía paso a paso para dejar el agente listo. Podés editar todo después desde cada sección.
        </p>
      </div>

      {/* Stepper */}
      <div className="mb-6 flex flex-wrap items-center gap-2">
        {STEPS.map((s, i) => {
          const Icon = s.icon
          const done = i < step
          const active = i === step
          return (
            <button
              key={s.id}
              onClick={() => setStep(i)}
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                active ? 'bg-hilton-600 text-white shadow-card'
                : done ? 'bg-hilton-50 text-hilton-700'
                : 'text-slatey hover:bg-mist'
              }`}
            >
              <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                active ? 'bg-white/20' : done ? 'bg-hilton-600 text-white' : 'bg-hilton-100 text-hilton-700'
              }`}>
                {done ? <Check size={13} /> : i + 1}
              </span>
              <Icon size={15} />
              <span className="hidden sm:inline">{s.label}</span>
            </button>
          )
        })}
      </div>

      {/* Ayuda del paso */}
      <div className="mb-4 rounded-xl border border-hilton-100 bg-hilton-50/40 px-4 py-3 text-sm text-ink">
        <span className="font-medium">Paso {step + 1} · {current.label}.</span> {current.help}
      </div>

      {/* Contenido del paso: la vista existente, embebida */}
      <div className="rounded-2xl border border-hilton-100 bg-white p-1 sm:p-2">
        {current.id === 'identidad' && <BusinessIdentityView />}
        {current.id === 'catalogo' && <HabitacionesView />}
        {current.id === 'conocimiento' && <KnowledgeView />}
        {current.id === 'tono' && <EmployeeHubSection />}
        {current.id === 'prueba' && <TestStep />}
      </div>

      {/* Navegación */}
      <div className="mt-5 flex items-center justify-between">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slatey hover:bg-mist disabled:opacity-40"
        >
          <ArrowLeft size={16} /> Anterior
        </button>
        {step < STEPS.length - 1 ? (
          <button
            onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
            className="flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700"
          >
            Siguiente <ArrowRight size={16} />
          </button>
        ) : (
          <a
            href="#admin/dashboard"
            className="flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2 text-sm font-medium text-white hover:bg-hilton-700"
          >
            <Check size={16} /> Finalizar
          </a>
        )}
      </div>
    </div>
  )
}

// Paso de prueba: checklist de go-live + acceso al chat público para probar el agente.
function TestStep() {
  const CHECKS = [
    'Preguntale el precio de una habitación → responde en la moneda correcta.',
    'Preguntá por algo que el hotel NO tiene → lo dice sin inventar (respeta los hechos).',
    'Pedile los datos de pago → da el CBU/alias exacto (si lo cargaste en Conocimiento).',
    'Saludalo casual → responde con el tono/idioma configurado.',
  ]
  return (
    <div className="p-4">
      <p className="mb-3 text-sm text-ink">
        Abrí el sitio público y hablá con el agente en el chat. Recorré este checklist antes del
        go-live:
      </p>
      <ul className="mb-5 space-y-2">
        {CHECKS.map((c, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-slatey">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-hilton-200 text-[11px] text-hilton-700">
              {i + 1}
            </span>
            {c}
          </li>
        ))}
      </ul>
      <a
        href="#inicio"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-2 rounded-xl bg-hilton-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-hilton-700"
      >
        <MessageCircle size={16} /> Abrir el sitio y probar el chat
      </a>
    </div>
  )
}
