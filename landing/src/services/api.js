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

export default client
