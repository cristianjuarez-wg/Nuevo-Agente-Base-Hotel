import axios from 'axios'

// Base del backend del hotel (puerto 8010). Configurable por env para el deploy.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8010'

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 90000,
})

// ── Reservas ───────────────────────────────────────────────────────────────
export async function getRooms() {
  const { data } = await client.get('/api/reservations/rooms')
  return data.rooms ?? data
}

export async function getAvailability({ checkIn, checkOut, guests }) {
  const { data } = await client.get('/api/reservations/availability', {
    params: { check_in: checkIn, check_out: checkOut, guests },
  })
  return data.available_rooms ?? data.rooms ?? data
}

export async function createBooking(payload) {
  // payload: { room_id, check_in, check_out, guest_name, guest_email, guest_phone, guests }
  const { data } = await client.post('/api/reservations/bookings', payload)
  return data.booking ?? data
}

export async function getBooking(code) {
  const { data } = await client.get(`/api/reservations/bookings/${code}`)
  return data.booking ?? data
}

// ── Chat del agente (Aura) ───────────────────────────────────────────────────
export async function getGreeting() {
  const { data } = await client.get('/api/chat/greeting')
  return data
}

export async function sendMessage({ message, sessionId }) {
  const { data } = await client.post('/api/chat/message', {
    message,
    session_id: sessionId,
  })
  return data
}

export async function clearChat(sessionId) {
  const { data } = await client.post(`/api/chat/clear/${sessionId}`)
  return data
}

// ── Backoffice ───────────────────────────────────────────────────────────────
export async function listBookings() {
  const { data } = await client.get('/api/reservations/bookings')
  return data.bookings ?? data
}

export async function listLeads() {
  const { data } = await client.get('/api/leads/active')
  // El endpoint devuelve { success, data: [...] }
  return data.data ?? data.leads ?? data
}

export async function listTickets() {
  const { data } = await client.get('/api/hotel-tickets')
  return data.tickets ?? data
}

export async function getTicketStats() {
  const { data } = await client.get('/api/hotel-tickets/stats')
  return data
}

// ── Consumo IA (tokens / USD) ────────────────────────────────────────────────
export async function getUsageSummary() {
  const { data } = await client.get('/api/usage/summary')
  return data
}

export async function getUsageConfig() {
  const { data } = await client.get('/api/usage/config')
  return data
}

export async function updateUsageConfig(payload) {
  // payload: { daily_limit_usd, monthly_limit_usd, enabled }
  const { data } = await client.put('/api/usage/config', payload)
  return data
}

// ── Repositorio de conocimiento (Agente) ─────────────────────────────────────
// Entradas estructuradas por categoría (pagos, checkin, cancelacion, mascotas, servicios, faq, general)
export async function listKnowledgeEntries(category) {
  const { data } = await client.get('/api/knowledge/entries', {
    params: category ? { category } : {},
  })
  return data.entries ?? data
}

export async function saveKnowledgeEntry(payload, id) {
  // payload: { category, title, content, data, status }
  if (id) {
    const { data } = await client.put(`/api/knowledge/entries/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/knowledge/entries', payload)
  return data
}

export async function setKnowledgeEntryStatus(id, status) {
  const { data } = await client.patch(`/api/knowledge/entries/${id}/status`, { status })
  return data
}

export async function deleteKnowledgeEntry(id) {
  const { data } = await client.delete(`/api/knowledge/entries/${id}`)
  return data
}

// Lugares / excursiones
export async function listPlaces(category) {
  const { data } = await client.get('/api/knowledge/places', {
    params: category ? { category } : {},
  })
  return data.places ?? data
}

export async function savePlace(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/knowledge/places/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/knowledge/places', payload)
  return data
}

export async function setPlaceStatus(id, status) {
  const { data } = await client.patch(`/api/knowledge/places/${id}/status`, { status })
  return data
}

export async function deletePlace(id) {
  const { data } = await client.delete(`/api/knowledge/places/${id}`)
  return data
}

// Subida de imagen → devuelve { url } (ruta /media/...). Se prefija con API_BASE para mostrarla.
export async function uploadKnowledgeImage(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/api/knowledge/upload-image', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// Config del agente (read-only): modelo, RAG, seguridad/rate-limit.
export async function getAdminConfig() {
  const { data } = await client.get('/api/admin/config')
  return data
}

// Base del backend, para resolver rutas /media/... a URLs absolutas.
export const MEDIA_BASE = API_BASE

export default client
