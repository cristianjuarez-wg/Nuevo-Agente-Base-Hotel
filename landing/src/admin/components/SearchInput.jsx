import { Search, X } from 'lucide-react'

/**
 * Input de búsqueda reutilizable del backoffice.
 * Props: value, onChange(string), placeholder
 */
export default function SearchInput({ value, onChange, placeholder = 'Buscar…' }) {
  return (
    <div className="relative w-full sm:max-w-xs">
      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slatey" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-hilton-200 py-2.5 pl-9 pr-9 text-sm focus:border-hilton-500 focus:outline-none focus:ring-2 focus:ring-hilton-100"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          aria-label="Limpiar búsqueda"
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slatey hover:bg-mist hover:text-ink"
        >
          <X size={15} />
        </button>
      )}
    </div>
  )
}
