/**
 * TEMA DE LA INSTANCIA — el único archivo a editar para cambiar la identidad visual.
 *
 * `brand` es el color de acento de toda la app (botones, links, estados activos, chips del
 * backoffice). Antes se llamaba `hilton` y estaba definido dentro de tailwind.config.js: el
 * nombre de un cliente era un token de diseño estructural, así que cada rubro nuevo heredaba
 * el azul de Hilton en cada botón (hallazgo F1 de la auditoría).
 *
 * Para una instancia nueva: cambiar los valores de `brand` (y opcionalmente los acentos) por
 * los de la marca del cliente. No hace falta tocar ningún componente.
 *
 * Nota: los acentos `sand`/`timber`/`stone`/`forest` son la paleta editorial "Patagonia" de
 * la landing del Hampton. La landing pública se rehace por proyecto (decisión F2), así que
 * viven acá como valores de la instancia actual, no como parte del núcleo.
 */

/** Color de marca (acento principal). Escala 50→900 + DEFAULT. */
export const brand = {
  DEFAULT: '#005aa9',
  50: '#e8f2fb',
  100: '#c5dcf5',
  200: '#9ec4ee',
  300: '#75ace6',
  400: '#4d95de',
  500: '#2d7edc',
  600: '#005aa9',
  700: '#004d90',
  800: '#003f77',
  900: '#002f5a',
}

/** Acentos editoriales de la landing (específicos de esta instancia). */
export const accents = {
  // Acento cálido (madera / patagonia)
  sand: {
    DEFAULT: '#c89b6a',
    50: '#faf6f0',
    100: '#f0e4d2',
    200: '#e3cba9',
    300: '#d4b184',
    400: '#c89b6a',
    500: '#b8854f',
    600: '#9c6e3f',
  },
  timber: {
    50: '#f7f3ee',
    100: '#ece2d4',
    200: '#d9c3a8',
    300: '#c2a279',
    400: '#a9824f',
    500: '#8a6a3f',
    600: '#6e5332',
  },
  stone: {
    50: '#f6f4f1',
    100: '#eceae4',
    200: '#dcd8cf',
    300: '#c3bdb0',
    400: '#a39c8c',
    500: '#827b6c',
    600: '#5f5a4e',
  },
  forest: {
    50: '#eef2ef',
    100: '#d6e0d8',
    200: '#aec2b2',
    300: '#7f9d86',
    400: '#577a60',
    500: '#3d5e46',
    600: '#2e4836',
  },
}

/** Neutros de texto y fondos (comunes a cualquier instancia). */
export const neutrals = {
  ink: '#1b2433',     // texto principal
  slatey: '#5b6b80',  // texto secundario
  mist: '#f4f7fb',    // fondo suave (azulado)
  linen: '#f7f4ee',   // fondo suave (cálido / papel)
}
