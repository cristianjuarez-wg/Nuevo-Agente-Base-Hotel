import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Landing pública del Hampton by Hilton Bariloche.
// Puerto 5174 para no chocar con el backoffice (5173) durante la demo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    host: true,
  },
})
