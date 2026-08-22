/**
 * Backend bilan aloqa qatlami.
 *
 * Barcha so'rovlar shu yerdan o'tadi — token, xatolik va
 * bazaviy URL bitta joyda boshqariladi.
 */

/** Backend manzili.
 *
 * Odatda `.env` dagi `VITE_API_URL` (masalan `http://localhost:8010`).
 * Ammo sahifa TUNNEL orqali telefonda ochilsa, `localhost` telefonning
 * o'zini bildiradi va u yerda backend yo'q. Shunday holatda bo'sh
 * qiymat qaytariladi: so'rovlar shu domenning o'ziga (`/api/v1/…`)
 * ketadi va Vite proxy'si ularni backend'ga uzatadi.
 *
 * Bu Telegram Mini App uchun majburiy — u faqat HTTPS domen orqali
 * ochiladi, `localhost` esa unga hech qachon yetib bormaydi.
 */
function resolveBaseUrl(): string {
  const configured = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  if (typeof window === 'undefined') return configured

  const host = window.location.hostname
  const onLocalhost = host === 'localhost' || host === '127.0.0.1' || host === '[::1]'
  if (onLocalhost) return configured

  // Sozlamada localhost turibdi-yu, sahifa boshqa domendan ochilgan —
  // sozlama bu muhitda ishlamaydi, same-origin ga o'tamiz
  if (/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/.test(configured)) {
    return ''
  }
  return configured
}

export const BASE_URL = resolveBaseUrl()
const API_PREFIX = '/api/v1'

const TOKEN_KEY = 'zvonki-token'
const REFRESH_KEY = 'zvonki-refresh'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/** Login talab qilmaydigan sahifalar.
 *
 * `/s` — Telegram Mini App so'rovnomasi. Uni do'kondor ochadi, uning
 * hech qanday akkaunti yo'q. Agar shu ro'yxatda bo'lmasa, brauzerda
 * eskirgan dashboard tokeni qolib ketgan bo'lsa, mijoz so'rovnoma
 * o'rniga login oynasini ko'rardi. */
const PUBLIC_PATHS = ['/login', '/s']

const isPublicPath = (pathname: string) =>
  PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_PREFIX}${path}`, BASE_URL)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, String(v)))
      } else {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.toString()
}

/**
 * Javobni yagona qoida bo'yicha o'qiydi: 401 — logindan chiqarish,
 * xato — `ApiError`, 204 — bo'sh natija.
 *
 * Alohida funksiya bo'lgani ataylab: JSON va fayl (`multipart`)
 * so'rovlari faqat TANASI bilan farq qiladi, javobni esa ikkalasi
 * ham bir xil o'qishi kerak. Ilgari fayl yuklash (avatar) buni
 * o'zicha takrorlab yozgan edi va u yerda 401 ushlanmasdi.
 */
async function unwrap<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    tokenStore.clear()
    if (!isPublicPath(location.pathname)) location.assign('/login')
    throw new ApiError(401, 'unauthorized', 'Avtorizatsiya talab qilinadi')
  }

  if (!response.ok) {
    let code = 'error'
    let message = `So'rov muvaffaqiyatsiz (${response.status})`
    try {
      const data = await response.json()
      code = data?.error?.code ?? data?.detail?.code ?? code
      message = data?.error?.message ?? data?.detail ?? message
    } catch {
      /* javob JSON emas — standart xabar qoladi */
    }
    throw new ApiError(response.status, code, message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function request<T>(
  method: string,
  path: string,
  options: { query?: Query; body?: unknown } = {},
): Promise<T> {
  const token = tokenStore.get()

  const response = await fetch(buildUrl(path, options.query), {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  return unwrap<T>(response)
}

/**
 * Fayl yuborish — `multipart/form-data`.
 *
 * ⚠️ `Content-Type` QO'LDA YOZILMAYDI va yozilmasligi kerak.
 * `multipart/form-data` sarlavhasining ichida `boundary=…` bo'ladi;
 * uni faqat brauzer biladi, chunki chegara satrini `FormData` ning
 * o'zi tasodifiy tanlaydi. Sarlavhani qo'lda yozsak chegara yo'qoladi
 * va server tanani umuman ajrata olmaydi — natija «422: field
 * required», ya'ni «fayl yubordim, lekin fayl yo'q» degan tushunarsiz
 * xato. Shuning uchun `headers` da faqat token qoladi.
 */
export async function postForm<T>(
  path: string,
  form: FormData,
  query?: Query,
): Promise<T> {
  const token = tokenStore.get()

  const response = await fetch(buildUrl(path, query), {
    method: 'POST',
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  })

  return unwrap<T>(response)
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
  postForm,
}
