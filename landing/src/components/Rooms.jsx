import { useEffect, useState } from 'react'
import { Users, BedDouble, Mountain, ArrowRight } from 'lucide-react'
import { getRooms } from '../services/api'
import { formatUSD, formatARS } from '../lib/format'
import Reveal, { RevealGroup, RevealItem } from './motion/Reveal'

const FALLBACK_IMG = '/fotos/habitacion-vista-lago.jpg'

function RoomCard({ room }) {
  const img = (room.images && room.images[0]) || FALLBACK_IMG
  return (
    <RevealItem
      as="article"
      className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-soft transition-shadow duration-500 hover:shadow-card-lg"
    >
      <div className="relative aspect-[4/5] overflow-hidden">
        <img
          src={img}
          alt={`Habitación ${room.room_type}`}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-[1.2s] ease-out group-hover:scale-[1.06]"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-ink/55 via-transparent to-transparent" />
        <span className="absolute left-4 top-4 rounded-full bg-linen/95 px-3.5 py-1 text-[11px] font-medium uppercase tracking-wide text-hilton-700 backdrop-blur">
          {room.room_type}
        </span>
        {/* Precio sobre la imagen, abajo */}
        <div className="absolute inset-x-4 bottom-4 flex items-end justify-between text-white">
          <div>
            <p className="text-[10px] uppercase tracking-eyebrow text-white/70">Desde / noche</p>
            <p className="font-display text-2xl font-600 leading-none tabular-nums">
              {formatUSD(room.base_price_usd)}
            </p>
          </div>
          <p className="pb-1 text-xs tabular-nums text-white/80">
            {formatARS(room.base_price_ars)}
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-6">
        <h3 className="font-display text-2xl font-600 text-ink">{room.room_type}</h3>
        {room.description && (
          <p className="mt-2 text-sm leading-relaxed text-slatey line-clamp-2">
            {room.description}
          </p>
        )}

        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slatey">
          <li className="inline-flex items-center gap-1.5">
            <Users size={15} className="text-timber-400" />
            Hasta {room.capacity}
          </li>
          {room.bed_config && (
            <li className="inline-flex items-center gap-1.5">
              <BedDouble size={15} className="text-timber-400" />
              {room.bed_config}
            </li>
          )}
          {room.view && (
            <li className="inline-flex items-center gap-1.5">
              <Mountain size={15} className="text-timber-400" />
              {room.view}
            </li>
          )}
        </ul>

        <a
          href="#reservar"
          className="group/btn mt-6 inline-flex items-center gap-2 self-start border-b border-hilton/30 pb-0.5 text-sm font-medium text-hilton-700 transition hover:border-hilton"
        >
          Reservar esta habitación
          <ArrowRight size={15} className="transition-transform group-hover/btn:translate-x-1" />
        </a>
      </div>
    </RevealItem>
  )
}

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-soft">
      <div className="aspect-[4/5] animate-pulse bg-stone-100" />
      <div className="space-y-3 p-6">
        <div className="h-6 w-3/4 animate-pulse rounded bg-stone-100" />
        <div className="h-3 w-full animate-pulse rounded bg-stone-100" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-stone-100" />
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
    <section id="habitaciones" className="section-pad bg-linen">
      <div className="container-wide px-6 sm:px-10">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="eyebrow">Alojamiento</p>
          <h2 className="mt-4 font-display text-4xl font-500 text-ink sm:text-5xl">
            Habitaciones que abrazan
          </h2>
          <div className="rule mt-6" />
          <p className="mt-6 text-base leading-relaxed text-slatey">
            Espacios confortables, luz natural y la calidez de nuestra hospitalidad.
            Cada habitación, una invitación a descansar.
          </p>
        </Reveal>

        {error ? (
          <p className="text-center text-slatey">
            No pudimos cargar las habitaciones en este momento. Probá nuevamente más tarde.
          </p>
        ) : loading ? (
          <div className="grid grid-cols-1 gap-7 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : (
          <RevealGroup
            className="grid grid-cols-1 gap-7 sm:grid-cols-2 lg:grid-cols-3"
            stagger={0.12}
          >
            {rooms.map((room) => <RoomCard key={room.id} room={room} />)}
          </RevealGroup>
        )}
      </div>
    </section>
  )
}
