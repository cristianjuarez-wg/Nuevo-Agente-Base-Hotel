import { useState, useEffect } from 'react'
import { HOTEL } from '../data/hotelInfo'
// MEDIA_BASE == API_BASE (misma base del backend); api.js solo exporta MEDIA_BASE.
import { MEDIA_BASE as API_BASE } from '../services/api'

/**
 * Identidad del negocio para la landing pública (P2).
 *
 * Estado inicial = objeto HOTEL (fallback de fábrica del cliente actual) → la landing SIEMPRE
 * tiene marca, sin flash ni spinner. Al montar, hace fetch al endpoint público
 * `/api/public/business-profile` y pisa lo que traiga; si el backend está caído, queda HOTEL.
 *
 * Normaliza los nombres del endpoint (business_name/brand_line/agent_display_name) a las claves
 * de HOTEL (name/tagline/agentName) para que los componentes lean una sola forma. Cliente nuevo
 * NO edita hotelInfo.js ni rebuildea: la landing se adapta al perfil del backend.
 */
export function useBusinessProfile() {
  const [profile, setProfile] = useState(HOTEL)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/public/business-profile`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d || cancelled) return
        setProfile((p) => ({
          ...p,
          name: d.business_name ?? p.name,
          tagline: d.brand_line ?? p.tagline,
          city: d.city ?? p.city,
          regionLine: d.region_line ?? p.regionLine,
          agentName: d.agent_display_name ?? p.agentName,
          language: d.language ?? p.language,
          primaryCurrency: d.primary_currency ?? p.primaryCurrency,
          secondaryCurrency: d.secondary_currency ?? p.secondaryCurrency,
        }))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  return profile
}
