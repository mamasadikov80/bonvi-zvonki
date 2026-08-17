/**
 * Mini App ↔ backend.
 *
 * Ikkala endpoint ham OCHIQ: JWT yo'q. Autentifikatsiya — `init_data`
 * ichidagi Telegram imzosi. Token ham o'sha imzolangan matndan
 * (`start_param`) olinadi, shuning uchun alohida yuborilmaydi.
 *
 * `@/shared/api/client` dagi `api` ATAYLAB ishlatilmaydi: u 401 ni
 * ko'rsa tokenni tozalab `/login` ga otadi. Bu yerda 401 — «imzo
 * eskirgan» degani, va do'kondor login sahifasini ko'rmasligi kerak.
 * Faqat `BASE_URL` qayta ishlatiladi, u bitta manbada tursin.
 */

import { BASE_URL } from '@/shared/api/client'

const ENDPOINT = `${BASE_URL}/api/v1/surveys/webapp`

export interface RedFlagOption {
  key: string
  /** Yorliq SERVERDAN keladi — sahifada ro'yxat saqlanmaydi */
  label: string
}

export interface WebAppOpenResponse {
  token: string
  agent_name: string
  period_start: string
  period_end: string
  already_rated: boolean
  red_flags: RedFlagOption[]
}

export interface WebAppSubmitResponse {
  ok: boolean
  agent_name: string
  response_count: number
}

export interface SubmitPayload {
  csat: number
  comment: string | null
  red_flags: string[]
}

/**
 * Sahifa ko'rsatadigan xato sabablari.
 *
 * HTTP kodi emas, SABAB saqlanadi: ekranda «401» degan raqam emas,
 * o'zbekcha jumla chiqadi. Kalitlar `surveyApp.error.*` bilan bir xil.
 */
export type FailureReason =
  | 'unauthorized'
  | 'notFound'
  | 'expired'
  | 'alreadyRated'
  | 'invalid'
  | 'unavailable'
  | 'network'
  | 'server'

export class SurveyWebAppError extends Error {
  constructor(
    public reason: FailureReason,
    public status: number,
  ) {
    super(reason)
    this.name = 'SurveyWebAppError'
  }
}

/** Backend javobidagi mashina kaliti — matn emas, u tarjimaga tegishli */
async function errorCode(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as {
      error?: { code?: string }
      detail?: string | { code?: string }
    }
    if (typeof data?.detail === 'object' && data.detail?.code) return data.detail.code
    return data?.error?.code ?? ''
  } catch {
    return ''
  }
}

/**
 * 409 ikki xil bo'lishi mumkin: muddat o'tgan yoki allaqachon baholangan.
 * Backend kaliti aniq bo'lsa o'shanga ishonamiz, bo'lmasa kontekstga:
 * ochishda 409 — muddat, yuborishda 409 — takroriy baho.
 */
function conflictReason(code: string, fallback: FailureReason): FailureReason {
  const c = code.toLowerCase()
  if (c.includes('already') || c.includes('rated') || c.includes('duplicate')) {
    return 'alreadyRated'
  }
  if (c.includes('expired') || c.includes('closed') || c.includes('window')) {
    return 'expired'
  }
  return fallback
}

async function post<T>(
  path: string,
  body: unknown,
  conflictFallback: FailureReason,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${ENDPOINT}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    // Do'kon ichida internet uzilishi odatiy hol — buni alohida aytamiz
    throw new SurveyWebAppError('network', 0)
  }

  if (!response.ok) {
    const code = await errorCode(response)
    const reason: FailureReason =
      response.status === 401 || response.status === 403
        ? 'unauthorized'
        : response.status === 404
          ? 'notFound'
          : response.status === 409
            ? conflictReason(code, conflictFallback)
            : response.status === 422 || response.status === 400
              ? 'invalid'
              : response.status === 503
                ? 'unavailable'
                : 'server'
    throw new SurveyWebAppError(reason, response.status)
  }

  return (await response.json()) as T
}

export function openSurvey(initData: string) {
  return post<WebAppOpenResponse>('/open', { init_data: initData }, 'expired')
}

export function submitSurvey(initData: string, payload: SubmitPayload) {
  return post<WebAppSubmitResponse>(
    '/submit',
    {
      init_data: initData,
      csat: payload.csat,
      comment: payload.comment,
      red_flags: payload.red_flags,
    },
    'alreadyRated',
  )
}
