import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import Rooms from './components/Rooms'
import About from './components/About'
import BookingEngine from './components/BookingEngine'
import Services from './components/Services'
import Gallery from './components/Gallery'
import Location from './components/Location'
import Footer from './components/Footer'
import ChatWidget from './components/ChatWidget'
import AdminApp from './admin/AdminApp'

function isAdminRoute() {
  return window.location.hash.startsWith('#admin')
}

export default function App() {
  const [admin, setAdmin] = useState(isAdminRoute())

  useEffect(() => {
    const onHash = () => setAdmin(isAdminRoute())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  if (admin) return <AdminApp />

  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Rooms />
        <About />
        <BookingEngine />
        <Services />
        <Gallery />
        <Location />
      </main>
      <Footer />
      <ChatWidget />
    </>
  )
}
