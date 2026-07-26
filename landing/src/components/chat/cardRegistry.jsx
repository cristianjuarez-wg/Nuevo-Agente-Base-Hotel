/**
 * REGISTRY DE CARDS DEL CHAT — la parte de DOMINIO del widget.
 *
 * El ChatWidget es un shell genérico (burbujas, typewriter, 4 idiomas, tema dinámico, sesión
 * persistente, reconexión WS). Lo único hotelero que tenía adentro era un if-chain con los
 * tipos de card (`room`, `date_picker`, `menu_interactive`…) y sus imports (hallazgo F4).
 *
 * Ahora el shell no conoce ningún tipo de card: recorre este mapa. Un rubro nuevo reemplaza
 * ESTE archivo por el suyo (`{ tipo: Componente }`) y se lleva el widget entero sin tocarlo.
 *
 * Contrato de cada card: recibe `{ card, onAction, lang }`.
 *   - `card`: el objeto que mandó el backend (siempre trae `type`).
 *   - `onAction(payload)`: para que la card dispare un mensaje/acción en el chat.
 *   - `lang`: idioma actual del widget.
 *
 * `needsRef: true` marca las cards a las que el shell engancha un ref para hacer scroll
 * (hoy solo el date picker, para que el huésped vea el selector al aparecer).
 */
import RoomCard from './RoomCard'
import DatePickerCard from './DatePickerCard'
import MenuCard from './MenuCard'
import MenuOrderCard from './MenuOrderCard'
import TableReservationCard from './TableReservationCard'

export const CARD_REGISTRY = {
  room: { Component: RoomCard },
  date_picker: { Component: DatePickerCard, needsRef: true },
  menu_interactive: { Component: MenuOrderCard },
  table_reservation: { Component: TableReservationCard },
  menu: { Component: MenuCard },
}

export default CARD_REGISTRY
