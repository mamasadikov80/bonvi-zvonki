import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Docker (macOS/Windows) ichida fayl o'zgarishini ushlash uchun
    watch: { usePolling: true, interval: 300 },

    /* Tunnel orqali kirishga ruxsat.
     *
     * Vite notanish `Host` sarlavhasini rad etadi (DNS rebinding
     * himoyasi). Telegram Mini App HTTPS talab qilgani uchun sahifa
     * tunnel domeni orqali ochiladi — u ro'yxatda bo'lishi kerak.
     * Nuqta bilan boshlangan yozuv barcha subdomenlarni qamraydi,
     * tunnel manzili har safar o'zgargani uchun bu zarur. */
    allowedHosts: [
      '.trycloudflare.com',
      '.ngrok-free.app',
      '.ngrok.io',
      '.loca.lt',
      ...(process.env.VITE_ALLOWED_HOSTS?.split(',')
        .map((host) => host.trim())
        .filter(Boolean) ?? []),
    ],

    /* Backend'ni shu porqadan o'tkazamiz.
     *
     * Sahifa tunnel orqali telefonda ochilganda `localhost:8010`
     * TELEFONNING o'zini bildiradi — u yerda backend yo'q. Shuning
     * uchun `/api` va `/media` shu server orqali backend'ga uzatiladi
     * va sahifa bitta manzil bilan ishlaydi. */
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
