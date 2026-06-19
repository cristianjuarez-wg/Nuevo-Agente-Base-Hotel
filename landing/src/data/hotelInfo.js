// Datos estáticos del hotel (reales del Hampton by Hilton Bariloche).
// Las habitaciones se cargan dinámicamente desde el backend; esto es contenido fijo.

export const HOTEL = {
  name: 'Hampton by Hilton',
  city: 'Bariloche',
  tagline: 'El primer Hilton de la Patagonia',
  address: 'Libertad 290, San Carlos de Bariloche, Patagonia, Argentina',
  phone: '+54 294-474-6200',
  email: 'info@hamptonbariloche.com',
  instagram: '@hamptonbariloche',
  checkIn: '15:00',
  checkOut: '11:00',
  mapsQuery: 'Hampton by Hilton Bariloche, Libertad 290, San Carlos de Bariloche',
}

// Servicios destacados (lucide icon names resueltos en el componente)
export const SERVICES = [
  {
    icon: 'UtensilsCrossed',
    title: 'Plaza — Hampton\'s Kitchen House',
    desc: 'Restaurante del hotel con propuesta gastronómica regional e internacional.',
  },
  {
    icon: 'Coffee',
    title: 'Desayuno buffet incluido',
    desc: 'Desayuno buffet incluido en todas las tarifas para empezar el día con energía.',
  },
  {
    icon: 'Wine',
    title: 'Lobby Bar',
    desc: 'Un espacio cálido para una copa o un café frente al corazón de Bariloche.',
  },
  {
    icon: 'Wifi',
    title: 'WiFi gratuito',
    desc: 'Conexión de alta velocidad en habitaciones y espacios comunes.',
  },
  {
    icon: 'Car',
    title: 'Estacionamiento cubierto',
    desc: 'Estacionamiento privado y cubierto con acceso directo (con costo adicional).',
  },
  {
    icon: 'Snowflake',
    title: 'Ski storage',
    desc: 'Guardado de equipos de esquí para tu temporada en la montaña.',
  },
  {
    icon: 'PawPrint',
    title: 'Pet friendly',
    desc: 'Tu mascota es bienvenida (consultá condiciones al reservar).',
  },
  {
    icon: 'Award',
    title: 'Hilton Honors',
    desc: 'Sumá puntos y disfrutá de los beneficios del programa de fidelidad Hilton.',
  },
]

// Razones / ubicación
export const HIGHLIGHTS = [
  { icon: 'MapPin', label: 'A 150 m del Centro Cívico' },
  { icon: 'Plane', label: 'A 20 min del aeropuerto internacional' },
  { icon: 'Mountain', label: 'Cercano al lago Nahuel Huapi' },
  { icon: 'Leaf', label: 'Sustentabilidad Nivel Plata' },
]
