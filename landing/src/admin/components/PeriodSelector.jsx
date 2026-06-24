import { FilterChip } from './FilterChip'

// Selector de período para el Dashboard y Analíticas. Los `id` coinciden con lo que
// resolve_period entiende en el backend (mes/trimestre/anio/semana/hoy), así no hay
// traducción: el valor viaja tal cual como query param `period`.
const PERIODS = [
  { id: 'hoy', label: 'Hoy' },
  { id: 'semana', label: 'Semana' },
  { id: 'mes', label: 'Mes' },
  { id: 'trimestre', label: 'Trimestre' },
  { id: 'anio', label: 'Año' },
]

export default function PeriodSelector({ value, onChange }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {PERIODS.map((p) => (
        <FilterChip
          key={p.id}
          active={value === p.id}
          onClick={() => onChange(p.id)}
          label={p.label}
        />
      ))}
    </div>
  )
}
