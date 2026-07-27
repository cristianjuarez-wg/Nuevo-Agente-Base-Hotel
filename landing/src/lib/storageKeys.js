// Keys de storage con nombre NEUTRO (higiene #12): sin marca de cliente ni del agente.
//
// Migración suave de las keys viejas (hampton_*/aura_*): si la key vieja existe, se copia
// a la nueva y se borra la vieja — una sola vez, en el primer load tras el cambio. Así un
// admin logueado NO se desloguea y la sesión de chat del huésped no se pierde.
export function migrateStorageKey(storage, oldKey, newKey) {
  try {
    const old = storage.getItem(oldKey)
    if (old != null) {
      if (storage.getItem(newKey) == null) storage.setItem(newKey, old)
      storage.removeItem(oldKey)
    }
  } catch { /* storage no disponible (modo privado, etc.) */ }
}
