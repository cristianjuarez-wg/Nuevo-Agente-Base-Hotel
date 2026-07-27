// Identidad de FALLBACK de la landing: placeholder NEUTRO, sin datos de ningún cliente real.
//
// La identidad real la sirve el backend en `/api/public/business-profile` y la aplica
// `useBusinessProfile()`, que usa este objeto solo como estado inicial (evita el flash sin marca
// mientras carga) y como red si el backend está caído. Un cliente nuevo NO edita este archivo:
// carga su perfil en el backoffice.
//
// NO poner acá datos reales de un cliente (dirección, teléfono, email): quedarían como estado
// inicial de CUALQUIER instancia y se filtrarían entre clientes.
export const HOTEL = {
  name: 'Su Negocio',
  city: '',
  tagline: '',
  address: '',
  phone: '',
  email: '',
  instagram: '',
  checkIn: '15:00',
  checkOut: '11:00',
  mapsQuery: '',
}

// Servicios destacados (lucide icon names resueltos en el componente).
// Contenido de DOMINIO de la instancia actual (criterio F2): la landing pública se rehace
// por proyecto, así que SERVICES/HIGHLIGHTS NO se parametrizan ni se mueven al núcleo.
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
