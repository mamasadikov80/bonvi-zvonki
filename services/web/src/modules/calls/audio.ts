/**
 * Qo'ng'iroq yozuvi bilan ishlash qatlami.
 *
 * ── Asosiy muammo va uning yechimi ────────────────────────────
 * Backend `GET /calls/{id}/audio` ni JWT bilan himoyalaydi, lekin
 * `<audio src="…">` ga `Authorization` sarlavhasini qo'shib bo'lmaydi.
 * Ya'ni «oddiy src» har doim 401 bilan tugaydi.
 *
 * Ikkita yo'l bor edi:
 *
 *   1. `fetch` + `blob:` — token qo'shiladi, lekin BUTUN fayl oldindan
 *      yuklanadi va `Range` backendga umuman bormaydi. 8 daqiqalik
 *      yozuvda 6-daqiqaga o'tish uchun avval hammasini kutish kerak.
 *
 *   2. Service Worker ko'prigi — SW so'rovni ushlab, `Authorization`
 *      qo'shib qayta yuboradi. `<audio>` esa oddiy URL bilan ishlaydi:
 *      brauzerning o'z pleeri `Range` so'rovlarini yuboradi, backend
 *      206 qaytaradi, seek NATIV ishlaydi.
 *
 * Asosiy yo'l — 2 (`public/audio-sw.js`). SW ishlamaydigan muhitda
 * (eski brauzer, `http://` LAN manzili — secure context emas) 1-yo'lga
 * tushib qolamiz: seek baribir ishlaydi, faqat butun fayl kutiladi.
 *
 * ── Nega manzil DOIM shu domendan olinadi ─────────────────────
 * Backend CORS da `expose_headers` yo'q. Boshqa domendan so'ralsa
 * brauzer `Content-Range` ni JS ga ham, SW javobiga ham bermaydi va
 * seek buziladi. `/api` esa dev'da Vite proxy, prod'da nginx orqali
 * shu domenning o'zidan o'tadi — sarlavhalar to'liq yetib keladi.
 */

import { useQuery } from '@tanstack/react-query'

import { tokenStore } from '@/shared/api/client'

/** Yozuv manzili — HAR DOIM same-origin (yuqoridagi izohga qarang) */
export const callAudioUrl = (callId: string) => `/api/v1/calls/${callId}/audio`

/* ── Yozuv holati ─────────────────────────────────────────────
   Pleerni ko'r-ko'rona chizib, keyin «error» hodisasini kutish yomon
   yechim: `<audio>` elementi xato SABABINI aytmaydi (na 404, na 503).
   Shuning uchun sahifa ochilganda bitta ARZON so'rov yuboriladi —
   `Range: bytes=0-0`, ya'ni bir bayt. Shundan keyin holat aniq:
   yozuv bor / yozuv yo'q / MoyZvonki sozlanmagan. */

export interface AudioAvailable {
  ok: true
  /** Backend `Range` ni qo'llab-quvvatlaydimi (206 qaytardimi) */
  ranges: boolean
  /** Umumiy hajm — `Content-Range: bytes 0-0/12345` dan */
  bytes: number | null
}

export interface AudioProblem {
  ok: false
  status: number
  code: string
  /** Backendning o'zbekcha izohi — foydalanuvchiga shu ko'rsatiladi */
  message: string
}

export type AudioProbe = AudioAvailable | AudioProblem

const NETWORK_PROBLEM: AudioProblem = {
  ok: false,
  status: 0,
  code: 'network',
  message: "Server bilan aloqa yo'q",
}

function authHeaders(extra?: Record<string, string>): HeadersInit {
  const token = tokenStore.get()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

/** Bir baytlik so'rov: yozuv umuman mavjudmi? */
export async function probeCallAudio(callId: string): Promise<AudioProbe> {
  let response: Response
  try {
    response = await fetch(callAudioUrl(callId), {
      method: 'GET',
      headers: authHeaders({ Range: 'bytes=0-0' }),
      credentials: 'include',
      cache: 'no-store',
    })
  } catch {
    return NETWORK_PROBLEM
  }

  if (response.ok) {
    // Tanani o'qimaymiz — oqim shu yerda uziladi, bir bayt ham
    // xotirada qolmaydi
    await response.body?.cancel().catch(() => undefined)
    const contentRange = response.headers.get('Content-Range')
    const total = contentRange?.split('/')[1]
    return {
      ok: true,
      ranges: response.status === 206,
      bytes: total && /^\d+$/.test(total) ? Number(total) : null,
    }
  }

  let code = 'error'
  let message = `So'rov muvaffaqiyatsiz (${response.status})`
  try {
    const data = await response.json()
    code = data?.error?.code ?? code
    message = data?.error?.message ?? message
  } catch {
    /* javob JSON emas — standart xabar qoladi */
  }
  return { ok: false, status: response.status, code, message }
}

export const useCallAudioProbe = (callId: string | undefined) =>
  useQuery({
    queryKey: ['call-audio', callId],
    queryFn: () => probeCallAudio(callId as string),
    enabled: Boolean(callId),
    // Yozuvning bor-yo'qligi bir sahifa ochilishida o'zgarmaydi
    staleTime: 5 * 60_000,
    retry: false,
  })

/* ── Service Worker ko'prigi ──────────────────────────────────── */

const SW_URL = '/audio-sw.js'

let bridge: Promise<boolean> | null = null

/** SW ro'yxatdan o'tguncha va sahifani boshqarguncha kutamiz */
async function takeControl(): Promise<ServiceWorker | null> {
  await navigator.serviceWorker.register(SW_URL, { scope: '/' })
  await navigator.serviceWorker.ready

  if (navigator.serviceWorker.controller) {
    return navigator.serviceWorker.controller
  }

  // Birinchi ro'yxatdan o'tishda sahifa hali boshqarilmaydi — SW
  // `clients.claim()` chaqirgach `controllerchange` keladi
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      navigator.serviceWorker.removeEventListener('controllerchange', onChange)
      resolve(null)
    }, 4000)

    function onChange() {
      clearTimeout(timer)
      navigator.serviceWorker.removeEventListener('controllerchange', onChange)
      resolve(navigator.serviceWorker.controller)
    }

    navigator.serviceWorker.addEventListener('controllerchange', onChange)
  })
}

/** Tokenni SW ga uzatib, tasdiqni kutamiz */
function sendToken(worker: ServiceWorker, token: string): Promise<boolean> {
  return new Promise((resolve) => {
    const channel = new MessageChannel()
    const timer = setTimeout(() => resolve(false), 2000)

    channel.port1.onmessage = (event) => {
      clearTimeout(timer)
      resolve(Boolean(event.data?.ok))
    }

    worker.postMessage({ type: 'zvonki-audio-token', token }, [channel.port2])
  })
}

/**
 * «Play» bosilishidan oldin chaqiriladi.
 *
 * `true` — SW tayyor, `<audio>` ni to'g'ridan-to'g'ri manzil bilan
 * ishlatsa bo'ladi (Range + seek nativ).
 * `false` — ko'prik yo'q, chaqiruvchi `blob:` yo'liga o'tadi.
 */
export function prepareAudioBridge(): Promise<boolean> {
  if (bridge) return bridge

  bridge = (async () => {
    const token = tokenStore.get()
    if (!token) return false
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
      return false
    }
    // `http://` LAN manzili secure context emas — SW ro'yxatdan o'tmaydi
    if (!window.isSecureContext) return false

    try {
      const worker = await takeControl()
      if (!worker) return false
      return await sendToken(worker, token)
    } catch {
      return false
    }
  })()

  // Muvaffaqiyatsizlikni keshlab qo'ymaymiz — keyingi urinish yangidan
  // boshlanadi (masalan token endi mavjud bo'lsa)
  bridge = bridge.then((ok) => {
    if (!ok) bridge = null
    return ok
  })

  return bridge
}

/**
 * Zaxira yo'l: butun yozuvni token bilan olib, `blob:` manzil yasaymiz.
 *
 * Seek shundan keyin ham ishlaydi, lekin xotirada — backendga `Range`
 * bormaydi. Faqat SW ishlamaydigan muhitda ishlatiladi.
 */
export async function fetchAudioAsObjectUrl(callId: string): Promise<string> {
  const response = await fetch(callAudioUrl(callId), {
    method: 'GET',
    headers: authHeaders(),
    credentials: 'include',
    cache: 'no-store',
  })

  if (!response.ok) {
    let message = `Yozuvni olishda xatolik (${response.status})`
    try {
      const data = await response.json()
      message = data?.error?.message ?? message
    } catch {
      /* JSON emas */
    }
    throw new Error(message)
  }

  return URL.createObjectURL(await response.blob())
}
