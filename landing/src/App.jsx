import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Rooms from './components/Rooms'
import About from './components/About'
import BookingEngine from './components/BookingEngine'
import Services from './components/Services'
import Restaurant from './components/Restaurant'
import Gallery from './components/Gallery'
import Location from './components/Location'
import Footer from './components/Footer'
import ChatWidget from './components/ChatWidget'
import RestaurantOrderPage from './components/restaurant/RestaurantOrderPage'
import AdminApp from './admin/AdminApp'
import LoginGate from './admin/LoginGate'

function currentRoute() {
  const h = window.location.hash
  if (h.startsWith('#admin')) return 'admin'
  if (h.startsWith('#pedido')) return 'pedido'
  return 'home'
}

export default function App() {
  const [route, setRoute] = useState(currentRoute())

  useEffect(() => {
    const onHash = () => setRoute(currentRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  if (route === 'admin') return <LoginGate><AdminApp /></LoginGate>
  if (route === 'pedido') return <RestaurantOrderPage />

  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Rooms />
        <About />
        <BookingEngine />
        <Services />
        <Restaurant />
        <Gallery />
        <Location />
      </main>
      <Footer />
      <ChatWidget />
    </>
  )
}
