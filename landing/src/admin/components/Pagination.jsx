import { ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * Controles de paginación del backoffice. Se oculta si hay una sola página.
 * Props: page (1-based), pageSize, total, onPageChange(page)
 */
export default function Pagination({ page, pageSize, total, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (totalPages <= 1) return null

  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <div className="mt-4 flex items-center justify-between gap-3 text-sm">
      <span className="text-slatey">
        <span className="tabular-nums">{from}–{to}</span> de <span className="tabular-nums">{total}</span>
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Página anterior"
          className="inline-flex items-center gap-1 rounded-lg border border-hilton-200 px-3 py-1.5 text-slatey transition hover:bg-mist disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <ChevronLeft size={15} /> Anterior
        </button>
        <span className="tabular-nums text-slatey">{page} / {totalPages}</span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Página siguiente"
          className="inline-flex items-center gap-1 rounded-lg border border-hilton-200 px-3 py-1.5 text-slatey transition hover:bg-mist disabled:opacity-40 disabled:hover:bg-transparent"
        >
          Siguiente <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}
