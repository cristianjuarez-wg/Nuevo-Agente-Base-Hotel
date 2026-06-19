// Galería con imágenes reales del CDN del hotel.
const IMAGES = [
  {
    src: 'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_30-1920w.jpg',
    alt: 'Habitación con vista del Hampton by Hilton Bariloche',
    span: 'sm:col-span-2 sm:row-span-2',
  },
  {
    src: 'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_02-0b2b9eb8-1920w.jpg',
    alt: 'Habitación King del hotel',
  },
  {
    src: 'https://lirp.cdn-website.com/02afd0e4/dms3rep/multi/opt/BRCHXHX_HAB_11-8766d766-1920w.jpg',
    alt: 'Habitación Twin del hotel',
  },
]

export default function Gallery() {
  return (
    <section id="galeria" className="section-pad bg-mist">
      <div className="container-x">
        <header className="mx-auto mb-12 max-w-2xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-hilton-500">
            Galería
          </p>
          <h2 className="font-serif text-3xl font-700 text-ink sm:text-4xl">
            Conocé el hotel
          </h2>
        </header>

        <div className="grid auto-rows-[180px] grid-cols-1 gap-4 sm:grid-cols-3 sm:auto-rows-[200px]">
          {IMAGES.map((img) => (
            <div
              key={img.src}
              className={`overflow-hidden rounded-2xl shadow-card ${img.span || ''}`}
            >
              <img
                src={img.src}
                alt={img.alt}
                loading="lazy"
                className="h-full w-full object-cover transition duration-500 hover:scale-105"
              />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
