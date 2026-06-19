import Reveal from './motion/Reveal'

// Galería con fotos profesionales reales del hotel (descargadas a public/fotos).
const IMAGES = [
  {
    src: '/fotos/lobby.jpg',
    alt: 'Lobby del Hampton by Hilton Bariloche con madera, piedra y diseño patagónico',
    span: 'sm:col-span-2 sm:row-span-2',
  },
  {
    src: '/fotos/lounge.jpg',
    alt: 'Lounge con sillones de cuero y diseño cálido',
  },
  {
    src: '/fotos/bar.jpg',
    alt: 'Lobby Bar del hotel con barra de madera y piedra',
  },
  {
    src: '/fotos/habitacion-vista-lago.jpg',
    alt: 'Habitación con vista al lago Nahuel Huapi',
  },
  {
    src: '/fotos/estar.jpg',
    alt: 'Estar con pared de piedra y mobiliario de madera',
    span: 'sm:col-span-2',
  },
]

export default function Gallery() {
  return (
    <section id="galeria" className="section-pad bg-ink">
      <div className="container-wide px-6 sm:px-10">
        <Reveal className="mx-auto mb-16 max-w-2xl text-center">
          <p className="eyebrow-light">Galería</p>
          <h2 className="mt-4 font-display text-4xl font-500 text-white sm:text-5xl">
            Un rincón de la Patagonia
          </h2>
          <div className="rule mt-6 bg-sand-400/60" />
        </Reveal>

        <Reveal
          className="grid auto-rows-[200px] grid-cols-1 gap-4 sm:grid-cols-3 sm:auto-rows-[230px]"
          y={32}
        >
          {IMAGES.map((img) => (
            <figure
              key={img.src}
              className={`group relative overflow-hidden rounded-2xl ${img.span || ''}`}
            >
              <img
                src={img.src}
                alt={img.alt}
                loading="lazy"
                className="h-full w-full object-cover transition-transform duration-[1.4s] ease-out group-hover:scale-[1.07]"
              />
              <div className="absolute inset-0 bg-ink/10 transition-colors duration-500 group-hover:bg-ink/0" />
            </figure>
          ))}
        </Reveal>
      </div>
    </section>
  )
}
