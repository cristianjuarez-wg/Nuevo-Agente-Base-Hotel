import { useEffect, useState } from 'react'
import { Users, BedDouble, Mountain, Check } from 'lucide-react'
import { getRooms } from '../services/api'

const FALLBACK_IMG =
  'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg'

function formatARS(n) {
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

function RoomCard({ room }) {
  const img = (room.images && room.images[0]) || FALLBACK_IMG
  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-card transition hover:shadow-card-lg">
      <div className="relative aspect-[4/3] overflow-hidden">
        <img
          src={img}
          alt={`Habitación ${room.room_type} del Hampton by Hilton Bariloche`}
          loading="lazy"
          className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
        />
        <span className="absolute left-3 top-3 rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-hilton-700 shadow-card backdrop-blur">
          {room.room_type}
        </span>
      </div>

      <div className="flex flex-1 flex-col p-5">
        {room.description && (
          <p className="mb-4 text-sm leading-relaxed text-slatey line-clamp-3">
            {room.description}
          </p>
        )}

        <ul className="mb-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slatey">
          <li className="inline-flex items-center gap-1.5">
            <Users size={15} className="text-hilton-500" />
            Hasta {room.capacity}
          </li>
          {room.bed_config && (
            <li className="inline-flex items-center gap-1.5">
              <BedDouble size={15} className="text-hilton-500" />
              {room.bed_config}
            </li>
          )}
          {room.view && (
            <li className="inline-flex items-center gap-1.5">
              <Mountain size={15} className="text-hilton-500" />
              {room.view}
            </li>
          )}
        </ul>

        {room.amenities?.length > 0 && (
          <ul className="mb-5 grid grid-cols-1 gap-1.5 text-xs text-ink sm:grid-cols-2">
            {room.amenities.slice(0, 4).map((a) => (
              <li key={a} className="inline-flex items-center gap-1.5">
                <Check size={13} className="shrink-0 text-sand-500" />
                <span className="truncate">{a}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto flex items-end justify-between border-t border-mist pt-4">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-slatey">Desde / noche</p>
            <p className="font-serif text-xl font-700 tabular-nums text-hilton-700">
              USD {room.base_price_usd}
            </p>
            <p className="text-xs tabular-nums text-slatey">
              ARS {formatARS(room.base_price_ars)}
            </p>
          </div>
          <a href="#reservar" className="btn-primary px-4 py-2.5 text-xs">
            Reservar
          </a>
        </div>
      </div>
    </article>
  )
}

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-card">
      <div className="aspect-[4/3] animate-pulse bg-mist" />
      <div className="space-y-3 p-5">
        <div className="h-4 w-3/4 animate-pulse rounded bg-mist" />
        <div className="h-3 w-full animate-pulse rounded bg-mist" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-mist" />
        <div className="h-9 w-1/2 animate-pulse rounded bg-mist" />
      </div>
    </div>
  )
}

export default function Rooms() {
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    getRooms()
      .then((data) => alive && setRooms(Array.isArray(data) ? data : []))
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  return (
    <section id="habitaciones" className="section-pad bg-mist">
      <div className="container-x">
        <header className="mx-auto mb-12 max-w-2xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-hilton-500">
            Alojamiento
          </p>
          <h2 className="font-serif text-3xl font-700 text-ink sm:text-4xl">
            Nuestras habitaciones
          </h2>
          <p className="mt-3 text-base text-slatey">
            Espacios confortables pensados para tu descanso, con la calidez de la
            hospitalidad Hampton.
          </p>
        </header>

        {error ? (
          <p className="text-center text-slatey">
            No pudimos cargar las habitaciones en este momento. Probá nuevamente más tarde.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {loading
              ? Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)
              : rooms.map((room) => <RoomCard key={room.id} room={room} />)}
          </div>
        )}
      </div>
    </section>
  )
}
