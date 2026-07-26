/**
 * API del DOMINIO HOTELERO (F6).
 *
 * Reservas, habitaciones, restaurante, vouchers, promociones, tipo de cambio, equipo y
 * pasajeros. Un rubro nuevo reemplaza ESTE archivo por el suyo; `api/core.js` no cambia.
 *
 * Usa el mismo cliente axios (con interceptores de auth) que expone core.
 */
import { client } from './core'

// ── Reservas ───────────────────────────────────────────────────────────────
export async function getRooms() {
  const { data } = await client.get('/api/reservations/rooms')
  return data.rooms ?? data
}

// ── Promociones ─────────────────────────────────────────────────────────────

export async function listPromotions() {
  const { data } = await client.get('/api/promotions/')
  return data.promotions ?? []
}

export async function savePromotion(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/promotions/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/promotions/', payload)
  return data
}

export async function patchPromotionStatus(id, status) {
  const { data } = await client.patch(`/api/promotions/${id}/status`, { status })
  return data
}

export async function deletePromotion(id) {
  const { data } = await client.delete(`/api/promotions/${id}`)
  return data
}

// ── Habitaciones (backoffice CRUD) ───────────────────────────────────────────

export async function listRoomsAdmin() {
  const { data } = await client.get('/api/admin/rooms')
  return data   // { rooms: [...], exchange_rate: {...} }
}

export async function saveRoom(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/admin/rooms/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/admin/rooms', payload)
  return data
}

export async function patchRoomStatus(id, status) {
  const { data } = await client.patch(`/api/admin/rooms/${id}/status`, { status })
  return data
}

export async function deleteRoom(id) {
  const { data } = await client.delete(`/api/admin/rooms/${id}`)
  return data
}

// ── Tipo de cambio USD → ARS ─────────────────────────────────────────────────

export async function getExchangeRate() {
  const { data } = await client.get('/api/exchange-rate')
  return data   // { current: {rate, mode, source, updated_at}, config: {...} }
}

export async function updateExchangeRate(payload) {
  // payload: { mode?: "auto"|"manual", manual_rate?: number }
  const { data } = await client.put('/api/exchange-rate', payload)
  return data
}

// Atención humana (handoff): config de horario/guardia + disponibilidad actual (Fase 4).
export async function getHumanAttention() {
  const { data } = await client.get('/api/human-attention')
  return data   // { config: {enabled, on_call, schedule}, available_now }
}

export async function updateHumanAttention(payload) {
  // payload: { enabled?, on_call?, schedule? }
  const { data } = await client.put('/api/human-attention', payload)
  return data
}

// Config del agente (read-only): modelo, RAG, seguridad/rate-limit.
export async function getAdminConfig() {
  const { data } = await client.get('/api/admin/config')
  return data
}

// ── Pasajeros y Contactos (identidad 360°) ───────────────────────────────────
export async function listPassengers() {
  const { data } = await client.get('/api/contacts/passengers')
  return data.passengers ?? data
}

export async function listLeadContacts() {
  const { data } = await client.get('/api/contacts/leads-identity')
  return data.leads ?? data
}

export async function getContactStats() {
  const { data } = await client.get('/api/contacts/stats/overview')
  return data
}

export async function deleteContact(contactId) {
  const { data } = await client.delete(`/api/contacts/${contactId}`)
  return data
}

// Limpia las conversaciones (historial del agente) atadas a un teléfono. Útil para
// historiales huérfanos cuyo contacto ya no existe.
export async function clearConversationByPhone(phone) {
  const { data } = await client.post('/api/contacts/conversations/clear-by-phone', { phone })
  return data
}

export async function updateContact(contactId, fields) {
  // fields: { first_name?, last_name?, email?, phone_number? }
  const { data } = await client.patch(`/api/contacts/${contactId}`, fields)
  return data
}

export async function getGuestProfile(contactId) {
  const { data } = await client.get(`/api/contacts/${contactId}/profile`)
  return data.profile ?? data
}

export async function updateGuestPreferences(contactId, preferences) {
  const { data } = await client.patch(`/api/contacts/${contactId}/preferences`, { preferences })
  return data
}

// ── Equipo del hotel (staff/dueño para el agente multi-rol) ──────────────────
export async function listStaff() {
  const { data } = await client.get('/api/staff')
  return data.staff ?? []
}

export async function saveStaff(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/staff/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/staff', payload)
  return data
}

export async function setStaffActive(id, active) {
  const { data } = await client.patch(`/api/staff/${id}/status`, { active })
  return data
}

export async function deleteStaff(id) {
  const { data } = await client.delete(`/api/staff/${id}`)
  return data
}

// ── Restaurante (carta, pedidos, folio, stats) ───────────────────────────────
export async function listMenuPublic() {
  const { data } = await client.get('/api/restaurant/menu/public')
  return data.menu ?? []
}

export async function listMenuAdmin() {
  const { data } = await client.get('/api/restaurant/menu')
  return data   // { menu: [...], exchange_rate: {...} }
}

export async function saveMenuItem(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/restaurant/menu/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/restaurant/menu', payload)
  return data
}

export async function patchMenuStatus(id, status) {
  const { data } = await client.patch(`/api/restaurant/menu/${id}/status`, { status })
  return data
}

export async function deleteMenuItem(id) {
  const { data } = await client.delete(`/api/restaurant/menu/${id}`)
  return data
}

export async function createOrder(payload) {
  // payload: { items:[{menu_item_id,qty,notes}], session_id, fulfillment, payment_mode, ... }
  const { data } = await client.post('/api/restaurant/orders', payload)
  return data
}

export async function getOrder(code) {
  const { data } = await client.get(`/api/restaurant/orders/${code}`)
  return data
}

export async function validateBooking(code) {
  const { data } = await client.get(`/api/restaurant/validate-booking/${encodeURIComponent(code)}`)
  return data   // { valid, in_house, guest_name, room_number, booking_code } | { valid:false, reason }
}

export async function listOrders() {
  const { data } = await client.get('/api/restaurant/orders')
  return data.orders ?? []
}

export async function patchOrderStatus(code, status) {
  const { data } = await client.patch(`/api/restaurant/orders/${code}/status`, { status })
  return data
}

export async function getFolio(bookingCode) {
  const { data } = await client.get(`/api/restaurant/folio/${bookingCode}`)
  return data
}

export async function settleFolio(bookingCode) {
  const { data } = await client.post(`/api/restaurant/folio/${bookingCode}/settle`)
  return data
}

export async function getRestaurantStats() {
  const { data } = await client.get('/api/restaurant/stats')
  return data
}

// ── Reservas de mesa (Fase 2) ───────────────────────────────────────────────
export async function getRestaurantSlots() {
  const { data } = await client.get('/api/restaurant/slots')
  return data.slots ?? {}
}

export async function createTableReservation(payload) {
  // payload: { fecha, hora, party_size, guest_name, guest_phone?, booking_code?, session_id?, notes? }
  const { data } = await client.post('/api/restaurant/table-reservations', payload)
  return data
}

export async function listTableReservations(scope) {
  const { data } = await client.get('/api/restaurant/table-reservations', { params: scope ? { scope } : {} })
  return data.reservations ?? []
}

export async function patchTableReservationStatus(code, status) {
  const { data } = await client.patch(`/api/restaurant/table-reservations/${code}/status`, { status })
  return data
}

// ── Vouchers (Fase 3) ───────────────────────────────────────────────────────
export async function createVoucher(payload) {
  // payload: { items:[{menu_item_id,qty}], buyer_name, buyer_phone?, session_id?, notes? }
  const { data } = await client.post('/api/restaurant/vouchers', payload)
  return data
}

export async function listVouchers(status) {
  const { data } = await client.get('/api/restaurant/vouchers', { params: status ? { status } : {} })
  return data.vouchers ?? []
}

export async function getVoucher(code) {
  const { data } = await client.get(`/api/restaurant/vouchers/${code}`)
  return data
}

export async function redeemVoucher(code) {
  const { data } = await client.post(`/api/restaurant/vouchers/${code}/redeem`)
  return data
}
