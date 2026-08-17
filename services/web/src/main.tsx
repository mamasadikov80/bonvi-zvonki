import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { ErrorBoundary } from '@/shared/ui/ErrorBoundary'
import { AppRouter } from '@/app/router'
import '@/shared/i18n'
import '@/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Tashqi chegara — hech qanday holatda OQ EKRAN bo'lmasligi
            uchun. Ichkarida `AppShell` sahifa atrofida o'z chegarasini
            qo'yadi (u yiqilganda menyu tirik qoladi); bu esa qobiqdan
            TASHQARIDAGI yo'llarni ham qamraydi — `/s` (mijoz
            so'rovnomasi) va `/monitor`. Mijoz so'rovnomasida oq ekran
            eng yomon holat: do'kondor «ishlamayapti» deb yopib ketadi
            va baho umuman yig'ilmaydi. */}
        <ErrorBoundary scope="root">
          <AppRouter />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
