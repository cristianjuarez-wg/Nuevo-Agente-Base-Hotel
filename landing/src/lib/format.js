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

// Zona horaria de toda la app: Argentina (UTC-3). Las fechas siempre se MUESTRAN en
// esta zona, sin importar dónde corra el navegador. El backend ya manda las fechas con
// offset explícito (-03:00); este timeZone garantiza el resultado aun si no lo trajera.
const AR_TZ = 'America/Argentina/Buenos_Aires'

// Una fecha sin zona ("2026-06-25T18:09:03", sin Z ni offset) se interpreta como UTC
// (que es como la guarda el backend), no como hora local del navegador.
function parseDate(iso) {
  if (typeof iso === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso)) {
    return new Date(iso + 'Z')  // naive → asumir UTC
  }
  return new Date(iso)
}

// Fecha dd/mm/aaaa (en hora Argentina).
export function formatDate(iso) {
  if (!iso) return '—'
  try {
    const d = parseDate(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: AR_TZ })
  } catch {
    return iso
  }
}

// Fecha y hora: dd/mm/aaaa HH:mm (en hora Argentina).
export function formatDateTime(iso) {
  if (!iso) return '—'
  try {
    const d = parseDate(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString('es-AR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
      timeZone: AR_TZ,
    })
  } catch {
    return iso
  }
}
