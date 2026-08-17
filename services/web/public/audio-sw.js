/* ══════════════════════════════════════════════════════════════
   Qo'ng'iroq yozuvi uchun avtorizatsiya ko'prigi (Service Worker)
   ══════════════════════════════════════════════════════════════

   MUAMMO
   `<audio src="…">` elementiga `Authorization` sarlavhasini qo'shib
   bo'lmaydi — brauzer API si bunga imkon bermaydi. Backend esa JWT
   talab qiladi, ya'ni oddiy `src` DOIM 401 qaytaradi.

   NEGA `fetch` + `blob:` YETARLI EMAS
   Blob bilan butun fayl oldindan yuklab olinadi va seek faqat xotirada
   ishlaydi. 8 daqiqalik yozuvda menejer 6-daqiqaga o'tmoqchi bo'lsa,
   avval butun faylni kutishi kerak va backend `Range` ni umuman
   ko'rmaydi. Bu yerdagi maqsad — TESKARISI: brauzerning o'z pleeri
   206 (Range) so'rovlarini yuborsin.

   YECHIM
   Service Worker sahifadan chiqadigan so'rovlarni ushlab turadi va
   FAQAT `/api/v1/calls/<uuid>/audio` yo'liga `Authorization` qo'shib
   qayta yuboradi. `<audio>` elementi hech narsani bilmaydi: u oddiy
   URL ni ochadi, `Range` so'raydi, 206 oladi va seek nativ ishlaydi.

   Boshqa hech qanday so'rovga tegilmaydi (`respondWith` chaqirilmaydi),
   hech narsa keshlanmaydi — audio bizda saqlanmaydi degan qoida shu
   yerda ham amal qiladi (`cache: 'no-store'`).
   ══════════════════════════════════════════════════════════════ */

const AUDIO_PATH = /^\/api\/v1\/calls\/[0-9a-fA-F-]{36}\/audio$/

/** Token faqat xotirada turadi — SW to'xtasa sahifa qaytadan yuboradi */
let accessToken = null

self.addEventListener('install', () => {
  // Yangi versiya darhol ishga tushsin — eski SW ni kutib turmaydi
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  // Birinchi ro'yxatdan o'tishdayoq sahifani boshqarishni olamiz,
  // aks holda foydalanuvchi sahifani yangilamaguncha ishlamas edi
  event.waitUntil(self.clients.claim())
})

self.addEventListener('message', (event) => {
  const data = event.data
  if (!data || data.type !== 'zvonki-audio-token') return

  accessToken = data.token || null

  // Sahifa tokenning yetib borganini kutadi: tasdiqlamasak, birinchi
  // «Play» tokensiz ketib 401 olishi mumkin edi
  const port = event.ports && event.ports[0]
  if (port) port.postMessage({ ok: true })
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  let url
  try {
    url = new URL(request.url)
  } catch {
    return
  }

  // Faqat o'z domenimizdagi audio yo'li. Qolgan hamma so'rov —
  // HMR, rasm, API — bu yerdan tegilmasdan o'tadi
  if (url.origin !== self.location.origin) return
  if (!AUDIO_PATH.test(url.pathname)) return

  event.respondWith(withAuthorization(request))
})

async function withAuthorization(request) {
  const headers = new Headers()

  // `Range` ni O'ZGARTIRMASDAN uzatamiz — seek shu sarlavhaga bog'liq
  const range = request.headers.get('range')
  if (range) headers.set('Range', range)

  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  return fetch(
    new Request(request.url, {
      method: 'GET',
      headers,
      mode: 'same-origin',
      // cookie ham ketsin: backend `access_token` cookie'sini ham qabul
      // qiladi, ya'ni token yetib bormay qolsa ham zaxira yo'l bor
      credentials: 'include',
      cache: 'no-store',
      redirect: 'follow',
    }),
  )
}
