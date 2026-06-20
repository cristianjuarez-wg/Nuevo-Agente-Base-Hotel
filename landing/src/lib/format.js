/**
 * Formato argentino unificado para todo el portal (backoffice, sitio público y chat).
 *
 *   - Números: punto para miles, coma para decimales (es-AR).
 *   - USD se muestra como "USD 1.200"; pesos como "$ 1.260.000".
 *   - Fechas en formato día/mes/año (dd/mm/aaaa).
 *
 * Única fuente de verdad: importar desde acá en vez de reimplementar en cada componente.
 */

// Número con formato argentino. `decimals` fija la cantidad exacta de decimales.
export function formatNumber(n, decimals = 0) {
  if (n == null || n === '' || isNaN(Number(n))) return '—'
  return new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(n))
}

// Monto en dólares: "USD 1.200" (o "USD 1,9664" con decimals=4 para consumo IA).
export function formatUSD(n, decimals = 0) {
  if (n == null || n === '' || isNaN(Number(n))) return '—'
  return `USD ${formatNumber(n, decimals)}`
}

// Monto en pesos argentinos: "$ 1.260.000".
export function formatARS(n) {
  if (n == null || n === '' || isNaN(Number(n))) return '—'
  return `$ ${formatNumber(n, 0)}`
}

// Fecha dd/mm/aaaa.
export function formatDate(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return iso
  }
}

// Fecha y hora: dd/mm/aaaa HH:mm.
export function formatDateTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString('es-AR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}
