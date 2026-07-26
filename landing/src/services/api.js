/**
 * FACHADA del cliente API (F6).
 *
 * Este archivo tenía 956 líneas mezclando lo genérico (auth, chat, conversaciones, uso,
 * conocimiento, agentes, temas, analíticas, contactos) con lo hotelero (reservas,
 * habitaciones, restaurante, vouchers, promociones, tipo de cambio). Ahora el código vive
 * separado por frontera:
 *
 *   - `services/api/core.js`  → NÚCLEO reusable en cualquier rubro. Incluye el cliente axios
 *                               con los interceptores de auth (JWT / X-Admin-Key).
 *   - `services/api/hotel.js` → DOMINIO hotelero. Un rubro nuevo reemplaza ESTE archivo por
 *                               el suyo y `core.js` no se toca.
 *
 * Se mantiene como fachada a propósito: los ~48 consumidores siguen importando de un solo
 * lugar (`from '../services/api'`) sin cambiar una línea, y el split no arrastra un refactor
 * masivo de imports. Al extraer el núcleo se copia `api/core.js` y se escribe el
 * `api/<rubro>.js` que corresponda.
 */
export * from './api/core'
export * from './api/hotel'
