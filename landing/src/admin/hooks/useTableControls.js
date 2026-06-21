import { useState, useMemo, useEffect } from 'react'

/**
 * Centraliza búsqueda + ordenamiento + paginación EN MEMORIA para las tablas del backoffice.
 *
 * @param {Array}  rows      filas ya filtradas por chips externos (estado, etc.)
 * @param {Object} options
 *   - searchKeys: string[]  campos sobre los que busca el texto (substring, case-insensitive)
 *   - initialSort: { key, dir } orden inicial ('asc' | 'desc')
 *   - pageSize: number       tamaño de página (default 50)
 *   - sortAccessors: { [key]: (row) => value }  valores custom para ordenar una columna
 *
 * Devuelve: { pageRows, query, setQuery, sort, toggleSort, page, setPage, total, pageSize }
 */
export function useTableControls(rows, {
  searchKeys = [],
  initialSort = null,
  pageSize = 50,
  sortAccessors = {},
} = {}) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(initialSort)   // { key, dir } | null
  const [page, setPage] = useState(1)

  // Filtrado por texto
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) =>
      searchKeys.some((k) => {
        const v = r[k]
        return v != null && String(v).toLowerCase().includes(q)
      })
    )
  }, [rows, query, searchKeys])

  // Ordenamiento
  const sorted = useMemo(() => {
    if (!sort?.key) return filtered
    const accessor = sortAccessors[sort.key] || ((r) => r[sort.key])
    const dir = sort.dir === 'desc' ? -1 : 1
    return [...filtered].sort((a, b) => {
      const av = accessor(a)
      const bv = accessor(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv), 'es', { numeric: true }) * dir
    })
  }, [filtered, sort, sortAccessors])

  // Paginación
  const total = sorted.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, totalPages)
  const pageRows = useMemo(
    () => sorted.slice((safePage - 1) * pageSize, safePage * pageSize),
    [sorted, safePage, pageSize]
  )

  // Resetear a página 1 al cambiar búsqueda u orden, o si el set se achica.
  useEffect(() => { setPage(1) }, [query, sort])
  useEffect(() => { if (page > totalPages) setPage(1) }, [totalPages, page])

  const toggleSort = (key) => {
    setSort((prev) => {
      if (prev?.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null   // tercer click: vuelve al orden natural
    })
  }

  return { pageRows, query, setQuery, sort, toggleSort, page: safePage, setPage, total, pageSize }
}
