import axios from 'axios'

// Base del backend del hotel (puerto 8010). Configurable por env para el deploy.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8010'

// URL del WebSocket del chat en vivo, derivada de API_BASE (http->ws, https->wss). Mismo host
// del backend, así el Origin del handshake es válido. Devuelve la URL completa del canal de
// una sesión (el visitante recibe por acá las respuestas humanas en vivo).
export function chatWsUrl(sessionId) {
  const base = API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  return `${base}/api/conversations/ws/${encodeURIComponent(sessionId)}`
}

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 90000,
})

// ── Clave de administración (acciones críticas del backoffice) ───────────────
// Se guarda en sessionStorage (se borra al cerrar el navegador). El interceptor la
// adjunta como header X-Admin-Key en cada request; el backend solo la exige en los
// endpoints críticos (topes, cotización, reset/demo). El resto la ignora.
const ADMIN_KEY_STORAGE = 'hampton_admin_key'

export function setAdminKey(key) {
  if (key) sessionStorage.setItem(ADMIN_KEY_STORAGE, key)
}
export function getAdminKey() {
  return sessionStorage.getItem(ADMIN_KEY_STORAGE) || ''
}
export function clearAdminKey() {
  sessionStorage.removeItem(ADMIN_KEY_STORAGE)
}

// ── Token de sesión del backoffice (JWT, Fase 2.5) ───────────────────────────
// El login devuelve un JWT que se guarda en sessionStorage; el interceptor lo adjunta
// como Authorization: Bearer en cada request. Si el backend responde 401 (token
// ausente/expirado), se limpia y se emite un evento para que la UI muestre el login.
const AUTH_TOKEN_STORAGE = 'hampton_auth_token'

export function setAuthToken(token) {
  if (token) sessionStorage.setItem(AUTH_TOKEN_STORAGE, token)
}
export function getAuthToken() {
  return sessionStorage.getItem(AUTH_TOKEN_STORAGE) || ''
}
export function clearAuthToken() {
  sessionStorage.removeItem(AUTH_TOKEN_STORAGE)
}
export function isAuthenticated() {
  return !!getAuthToken()
}

export async function login(email, password) {
  const { data } = await client.post('/api/auth/login', { email, password })
  setAuthToken(data.access_token)
  return data.user
}
export function logout() {
  clearAuthToken()
}
export async function getMe() {
  const { data } = await client.get('/api/auth/me')
  return data
}

client.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  const key = getAdminKey()
  if (key) config.headers['X-Admin-Key'] = key
  return config
})

// En 401 (sesión ausente/expirada) limpiamos el token y avisamos a la UI (evento global)
// para que muestre el login, salvo que la request sea el propio login.
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    const url = error?.config?.url || ''
    if (status === 401 && !url.includes('/api/auth/login')) {
      clearAuthToken()
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    return Promise.reject(error)
  },
)

// ── Reservas ───────────────────────────────────────────────────────────────
export async function getRooms() {
  const { data } = await client.get('/api/reservations/rooms')
  return data.rooms ?? data
}

// ── Identidad del negocio (BusinessProfile, Fase 1) ──────────────────────────
export async function getBusinessProfile() {
  const { data } = await client.get('/api/business-profile')
  return data
}

export async function updateBusinessProfile(payload) {
  const { data } = await client.put('/api/business-profile', payload)
  return data
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

export async function deleteBooking(code) {
  const { data } = await client.delete(`/api/reservations/bookings/${code}`)
  return data
}

// Check-in express: dispara el flujo por WhatsApp para una reserva (acción protegida).
export async function sendCheckinExpress(code) {
  const { data } = await client.post(`/api/checkin/${encodeURIComponent(code)}/send`)
  return data
}

// ── Chat del agente (Aura) ───────────────────────────────────────────────────
export async function getGreeting(lang = 'es') {
  const { data } = await client.get('/api/chat/greeting', { params: { lang } })
  return data
}

export async function sendMessage({ message, sessionId, language = 'es' }) {
  const { data } = await client.post('/api/chat/message', {
    message,
    session_id: sessionId,
    language,
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

export async function listLeads(includeUnnamed = false, includeConverted = false) {
  // includeUnnamed=true suma los contactos crudos (teléfono sin nombre, ej. WhatsApp que consultó).
  // includeConverted=true suma los leads ya ganados/convertidos (que reservaron) — la lista los
  // muestra para no quedar vacía cuando un lead reserva (igual que el tablero).
  const params = {}
  if (includeUnnamed) params.include_unnamed = true
  if (includeConverted) params.include_converted = true
  const { data } = await client.get('/api/leads/active', { params })
  // El endpoint devuelve { success, data: [...] }
  return data.data ?? data.leads ?? data
}

export async function deleteLead(leadId) {
  const { data } = await client.delete(`/api/leads/${leadId}`)
  return data
}

export async function updateLead(leadId, fields) {
  // fields: { name?, last_name?, email?, phone? }
  const { data } = await client.patch(`/api/leads/${leadId}`, fields)
  return data
}

// Bitácora de actividad del lead: acciones de Aura (resumidas) + seguimientos humanos.
export async function listLeadEvents(leadId) {
  const { data } = await client.get(`/api/leads/${leadId}/events`)
  return data.data?.events ?? []
}

export async function addLeadFollowUp(leadId, note, actorName = '') {
  const { data } = await client.post(`/api/leads/${leadId}/events`, { note, actor_name: actorName || undefined })
  return data
}

// Genera bajo demanda un resumen IA de la charla del lead (lo agrega a la bitácora).
export async function summarizeLead(leadId) {
  const { data } = await client.post(`/api/leads/${leadId}/summarize`)
  return data
}

// Kanban de leads: tablero por etapa (new / contacted / won / lost).
export async function getKanbanLeads() {
  const { data } = await client.get('/api/kanban/leads')
  // { success, data: { new, contacted, won, lost }, stats }
  return { columns: data.data ?? {}, stats: data.stats ?? null }
}

export async function moveLeadStage(leadId, stage) {
  // stage ∈ new | contacted | won | lost. Sincroniza el status interno en el backend.
  const { data } = await client.put(`/api/kanban/leads/${leadId}/stage`, { stage })
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

export async function deleteTicket(ticketId) {
  const { data } = await client.delete(`/api/hotel-tickets/${ticketId}`)
  return data
}

export async function assignTicket(ticketId, payload) {
  const { data } = await client.patch(`/api/hotel-tickets/${ticketId}/assign`, payload)
  return data.ticket ?? data
}

export async function preResolveTicket(ticketId, note) {
  const { data } = await client.patch(`/api/hotel-tickets/${ticketId}/pre-resolve`, { note })
  return data.ticket ?? data
}

export async function resolveTicketAdmin(ticketId) {
  const { data } = await client.patch(`/api/hotel-tickets/${ticketId}/resolve`)
  return data.ticket ?? data
}

export async function reopenTicket(ticketId) {
  const { data } = await client.patch(`/api/hotel-tickets/${ticketId}/reopen`)
  return data.ticket ?? data
}

export async function setTicketPriority(ticketId, priority) {
  const { data } = await client.patch(`/api/hotel-tickets/${ticketId}/priority`, { priority })
  return data.ticket ?? data
}

// Transcripción de la charla con Aura que originó un ticket o un lead (por session_id).
export async function getConversation(sessionId) {
  const { data } = await client.get(`/api/conversations/${encodeURIComponent(sessionId)}/messages`)
  return data.messages ?? []
}

// Lista las conversaciones de un canal (por defecto WhatsApp): número, nombre (o sin nombre),
// cantidad de mensajes y fechas. Para ver quién se contactó aunque no haya dejado datos.
export async function listConversations(channel = 'whatsapp') {
  const { data } = await client.get('/api/conversations', { params: { channel } })
  return data.conversations ?? []
}

// ── Toma de control humana (takeover / HITL) ─────────────────────────────────
// Acciones críticas: el cliente ya adjunta X-Admin-Key automáticamente si está configurada.
export async function takeOverConversation(sessionId, { staffId = null, staffName = '' } = {}) {
  const { data } = await client.post(`/api/conversations/${encodeURIComponent(sessionId)}/takeover`,
    { staff_id: staffId, staff_name: staffName })
  return data
}

export async function releaseConversation(sessionId) {
  const { data } = await client.post(`/api/conversations/${encodeURIComponent(sessionId)}/release`)
  return data
}

// Elimina definitivamente una conversación (hilo + mensajes). No toca contacto/reservas.
export async function deleteConversation(sessionId) {
  const { data } = await client.delete(`/api/conversations/${encodeURIComponent(sessionId)}`)
  return data
}

export async function sendHumanReply(sessionId, message, { staffId = null, staffName = '' } = {}) {
  const { data } = await client.post(`/api/conversations/${encodeURIComponent(sessionId)}/reply`,
    { message, staff_id: staffId, staff_name: staffName })
  return data
}

// Todas las conversaciones de un contacto (web y WhatsApp; filtra por contact_id). Cada una
// trae session_id, channel, started_at y message_count para listarlas en el perfil 360°.
export async function getContactConversations(contactId) {
  const { data } = await client.get(`/api/contacts/${contactId}/conversations`, { params: { limit: 50 } })
  return data.conversations ?? []
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

// ── Analíticas (funnel, heatmap, canales) — filtrables por período ───────────
function _periodParam(period) {
  return period ? { period } : {}
}

export async function getFunnel(channel, period) {
  const { data } = await client.get('/api/analytics/funnel', {
    params: { ..._periodParam(period), ...(channel && channel !== 'all' ? { channel } : {}) },
  })
  return data.data ?? data
}

export async function getHeatmap(channel, period) {
  const { data } = await client.get('/api/analytics/conversations/heatmap', {
    params: { ..._periodParam(period), ...(channel && channel !== 'all' ? { channel } : {}) },
  })
  return data.data ?? data
}

export async function getAgentQualityMetrics(period) {
  const { data } = await client.get('/api/analytics/postsale/metrics', { params: _periodParam(period) })
  return data.data ?? data
}

export async function getChannelStats(period) {
  const { data } = await client.get('/api/analytics/conversations/channels', { params: _periodParam(period) })
  return data.data ?? data
}

// Dashboard period-aware: tarjetas de negocio filtradas + "en casa hoy" operativo.
export async function getDashboardSummary(period) {
  const { data } = await client.get('/api/analytics/dashboard', { params: _periodParam(period) })
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

// ── Conocimiento del Asesor de Gerencia (RAG separado del de Aura) ───────────
export async function listManagementDocs() {
  const { data } = await client.get('/api/management-knowledge/documents')
  return data.documents ?? []
}

export async function getManagementDocContent(filename) {
  const { data } = await client.get(
    `/api/management-knowledge/documents/${encodeURIComponent(filename)}/content`
  )
  return data
}

export async function uploadManagementDoc(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/api/management-knowledge/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
  return data
}

export async function uploadManagementText({ title, text }) {
  const { data } = await client.post('/api/management-knowledge/documents/text', { title, text })
  return data
}

export async function setManagementDocStatus(filename, status) {
  const { data } = await client.patch(
    `/api/management-knowledge/documents/${encodeURIComponent(filename)}/status`, { status }
  )
  return data
}

export async function deleteManagementDoc(filename) {
  const { data } = await client.delete(
    `/api/management-knowledge/documents/${encodeURIComponent(filename)}`
  )
  return data
}

export async function resetAdvisorMemory() {
  const { data } = await client.post('/api/management-knowledge/reset-advisor-memory')
  return data
}

// ── Datos de demostración (poblar / limpiar desde el backoffice) ─────────────
export async function getDemoStatus() {
  const { data } = await client.get('/api/demo/status')
  return data
}

export async function populateDemo() {
  const { data } = await client.post('/api/demo/populate')
  return data
}

export async function clearDemo() {
  const { data } = await client.post('/api/demo/clear')
  return data
}

// Borra TODO lo operativo (real + demo); conserva la config. Exige confirm === 'RESETEAR'.
export async function resetAllData(confirm) {
  const { data } = await client.post('/api/demo/reset-all', { confirm })
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

// ── Centro del Empleado Digital (agentes) ────────────────────────────────────
export async function listAgents() {
  const { data } = await client.get('/api/agents')
  return data.agents ?? []
}

export async function getAgent(id) {
  const { data } = await client.get(`/api/agents/${id}`)
  return data
}

export async function updateAgent(id, payload) {
  const { data } = await client.put(`/api/agents/${id}`, payload)
  return data
}

export async function getAgentPerformance(id, period = 'mes') {
  const { data } = await client.get(`/api/agents/${id}/performance`, { params: { period } })
  return data
}

// Capacidades legibles (grupos) del agente — para la zona "Qué puede hacer" de la ficha (F1.2).
export async function getAgentCapabilities(id) {
  const { data } = await client.get(`/api/agents/${id}/capabilities`)
  return data
}

export async function getAgentDailyReport(id) {
  const { data } = await client.get(`/api/agents/${id}/daily-report`)
  return data
}

export async function updateAgentDailyReportConfig(id, payload) {
  const { data } = await client.put(`/api/agents/${id}/daily-report/config`, payload)
  return data
}

export async function sendAgentDailyReport(id) {
  const { data } = await client.post(`/api/agents/${id}/daily-report/send`)
  return data
}

export async function listAgentTraining(id) {
  const { data } = await client.get(`/api/agents/${id}/training`)
  return data.documents ?? []
}

export async function uploadAgentTraining(id, { title, file }) {
  const form = new FormData()
  form.append('title', title)
  form.append('file', file)
  const { data } = await client.post(`/api/agents/${id}/training/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
  return data
}

export async function addAgentTrainingText(id, { title, text }) {
  const { data } = await client.post(`/api/agents/${id}/training/text`, { title, text })
  return data
}

export async function deleteAgentTraining(id, docId) {
  const { data } = await client.delete(`/api/agents/${id}/training/${docId}`)
  return data
}

export async function getTrainingSchemas() {
  const { data } = await client.get('/api/agents/training-schemas')
  return data
}

export async function createTrainingEntry(id, payload) {
  const { data } = await client.post(`/api/agents/${id}/training/entry`, payload)
  return data
}

export async function updateTrainingEntry(id, docId, payload) {
  const { data } = await client.put(`/api/agents/${id}/training/${docId}`, payload)
  return data
}

export async function restoreTrainingEntry(id, docId) {
  const { data } = await client.post(`/api/agents/${id}/training/${docId}/restore`)
  return data
}

export async function extractTraining(id, { category, file, text }) {
  const form = new FormData()
  form.append('category', category)
  if (file) form.append('file', file)
  if (text) form.append('text', text)
  const { data } = await client.post(`/api/agents/${id}/training/extract`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
  return data
}

export async function listAgentSkills(id) {
  const { data } = await client.get(`/api/agents/${id}/skills`)
  return data.skills ?? []
}

export async function listAgentFlows(id) {
  const { data } = await client.get(`/api/agents/${id}/skills`, { params: { kind: 'flow' } })
  return data.skills ?? []
}

export async function getCentroConfig() {
  const { data } = await client.get('/api/agents/centro-config')
  return data
}

export async function updateCentroConfig(payload) {
  const { data } = await client.put('/api/agents/centro-config', payload)
  return data
}

export async function updateAgentSkill(id, skillId, payload) {
  const { data } = await client.put(`/api/agents/${id}/skills/${skillId}`, payload)
  return data
}

// Base del backend, para resolver rutas /media/... a URLs absolutas.
export const MEDIA_BASE = API_BASE

export default client
