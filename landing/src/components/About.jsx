import Reveal from './motion/Reveal'
import { useBusinessProfile } from '../hooks/useBusinessProfile'

// Sección "El hotel" — split imagen/texto editorial, con la foto del lobby (madera + piedra).
export default function About() {
  const HOTEL = useBusinessProfile()
  return (
    <section className="bg-white">
      <div className="grid grid-cols-1 lg:grid-cols-2">
        {/* Imagen a sangre */}
        <div className="relative min-h-[60vw] overflow-hidden sm:min-h-[440px] lg:min-h-[640px]">
          <img
            src="/fotos/lobby.jpg"
            alt="Lobby del hotel, con madera, piedra y diseño patagónico"
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
          />
        </div>

        {/* Texto */}
        <div className="flex items-center px-6 py-16 sm:px-10 lg:px-16 lg:py-24">
          {/* F3: copy de instancia — reemplazar por cliente (relato de marca + geografía específica) */}
          <Reveal className="max-w-lg">
            <p className="eyebrow">Nuestra hospitalidad</p>
            <h2 className="mt-4 font-display text-4xl font-500 leading-tight text-ink sm:text-5xl">
              Hospitalidad cálida, en estado puro
            </h2>
            <div className="mt-6 h-px w-12 bg-timber-300" />
            <p className="mt-6 text-base leading-relaxed text-slatey">
              Maderas nobles, piedra de la región y la calidez que distingue a {HOTEL.name}.
              Cada espacio del hotel fue pensado para que te sientas en casa, con el confort
              de una marca global y el alma de la Patagonia.
            </p>
            <p className="mt-4 text-base leading-relaxed text-slatey">
              Amistosos, auténticos y siempre atentos: así es como queremos que recuerdes
              tu estadía en {HOTEL.city}.
            </p>
            <a href="#servicios" className="btn-secondary mt-8">
              Conocer los servicios
            </a>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
