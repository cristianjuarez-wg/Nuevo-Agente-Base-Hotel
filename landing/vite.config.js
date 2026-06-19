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
  build: {
    rollupOptions: {
      output: {
        // Separar libs pesadas en chunks propios para mejor cacheo y carga inicial.
        manualChunks: {
          motion: ['framer-motion'],
          markdown: ['react-markdown', 'remark-gfm'],
          vendor: ['react', 'react-dom', 'axios', 'date-fns'],
        },
      },
    },
  },
})
