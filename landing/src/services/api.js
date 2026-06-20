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

export async function deleteLead(leadId) {
  const { data } = await client.delete(`/api/leads/${leadId}`)
  return data
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

// Documentos libres (PDF o texto pegado) con categoría estandarizada.
export async function listKnowledgeDocuments() {
  const { data } = await client.get('/api/knowledge/documents')
  return data.documents ?? data
}

export async function uploadKnowledgeDocument({ title, category, file }) {
  const form = new FormData()
  form.append('title', title)
  form.append('category', category)
  form.append('file', file)
  const { data } = await client.post('/api/knowledge/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function uploadKnowledgeTextDocument({ title, category, text }) {
  const { data } = await client.post('/api/knowledge/documents/text', { title, category, text })
  return data
}

// Auto-completar formulario desde un documento (PDF o texto) con GPT-4o-mini.
// Devuelve { category, fields } con los campos sugeridos (el usuario revisa antes de guardar).
export async function extractFromDocument({ category, file, text }) {
  const form = new FormData()
  form.append('category', category)
  if (file) form.append('file', file)
  if (text) form.append('text', text)
  const { data } = await client.post('/api/knowledge/extract', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
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

// ── Temas visuales del chat (Fase 4) ────────────────────────────────────────

export async function getChatTheme() {
  const { data } = await client.get('/api/chat/theme')
  return data.theme ?? null
}

export async function listChatThemes() {
  const { data } = await client.get('/api/chat-themes/')
  return data.themes ?? []
}

export async function saveChatTheme(payload, id) {
  if (id) {
    const { data } = await client.put(`/api/chat-themes/${id}`, payload)
    return data
  }
  const { data } = await client.post('/api/chat-themes/', payload)
  return data
}

export async function patchChatThemeStatus(id, status) {
  const { data } = await client.patch(`/api/chat-themes/${id}/status`, { status })
  return data
}

export async function deleteChatTheme(id) {
  const { data } = await client.delete(`/api/chat-themes/${id}`)
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

// Config del agente (read-only): modelo, RAG, seguridad/rate-limit.
export async function getAdminConfig() {
  const { data } = await client.get('/api/admin/config')
  return data
}

// ── Analíticas (funnel, heatmap, canales) ────────────────────────────────────
export async function getFunnel(channel) {
  const { data } = await client.get('/api/analytics/funnel', {
    params: channel && channel !== 'all' ? { channel } : {},
  })
  return data.data ?? data
}

export async function getHeatmap(channel, days = 30) {
  const { data } = await client.get('/api/analytics/conversations/heatmap', {
    params: { days, ...(channel && channel !== 'all' ? { channel } : {}) },
  })
  return data.data ?? data
}

export async function getChannelStats() {
  const { data } = await client.get('/api/analytics/conversations/channels')
  return data.data ?? data
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

export async function getGuestProfile(contactId) {
  const { data } = await client.get(`/api/contacts/${contactId}/profile`)
  return data.profile ?? data
}

export async function updateGuestPreferences(contactId, preferences) {
  const { data } = await client.patch(`/api/contacts/${contactId}/preferences`, { preferences })
  return data
}

// Base del backend, para resolver rutas /media/... a URLs absolutas.
export const MEDIA_BASE = API_BASE

export default client
