/**
 * Client baholari (so'rovnoma javoblari) API qatlami.
 *
 * Backend `GET /api/v1/surveys` rolga sezgir:
 *   • admin / manager — barcha xodim, izohlar bilan
 *   • sales          — faqat o'ziniki; izohlar `access.sales_client_rating`
 *                      sozlamasiga bog'liq (full → bor, score_only → null,
 *                      hidden → 403)
 *
 * Client kimligi javobda umuman yo'q — baho anonim.
 */

import { useQuery } from '@tanstack/react-query'

import { api, ApiError } from '@/shared/api/client'

/* ── Reyting chegarasi ───────────────────────────────────────
   Chegara (`survey.min_responses`) — ADMIN SOZLAMASI. Shuning uchun
   bu yerda RAQAM YO'Q: ilgari `MIN_RESPONSES_FOR_RATING = 5`
   konstantasi bor edi va admin sozlamada 8 qilib qo'ysa, UI baribir
   «/5» deb yozib turardi.

   Yagona manba — javobning o'zi. Backend maydonni hali bermayotgan
   bo'lsa `min` `null` bo'ladi va UI maxrajsiz matnga tushadi
   («3 ta javob»), «3 / undefined» ko'rsatishdan ko'ra shu yaxshi. */

export interface RatingProgress {
  /** Nechta javob to'plangan */
  count: number
  /** O'rtacha ochilishi uchun kerakli javoblar soni — noma'lum bo'lsa `null` */
  min: number | null
  /** Yana nechta javob kerak — chegara noma'lum bo'lsa `null` */
  remaining: number | null
}

/** Har qanday reyting javobidan («count» + ixtiyoriy chegara) progress */
export function ratingProgress(
  source:
    | { count?: number | null; min_responses?: number | null }
    | null
    | undefined,
): RatingProgress {
  const raw = source?.count
  const count = typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : 0

  const limit = source?.min_responses
  const min =
    typeof limit === 'number' && Number.isFinite(limit) && limit > 0 ? limit : null

  return { count, min, remaining: min == null ? null : Math.max(0, min - count) }
}

export type Resolution = 'yes' | 'partial' | 'no'

export interface SurveyFeedbackItem {
  id: string
  agent_id: string
  agent_name: string
  /** 1..5 yulduz */
  csat: number
  resolution: Resolution | null
  /** `null` — izoh yo'q YOKI sozlama izohlarni yopgan */
  comment: string | null
  responded_at: string
  /** Hudud endi XODIMDAN emas, so'rovnoma yuborilgan GURUHDAN keladi */
  region: string
  /**
   * Tanlangan qoidabuzarlik kalitlari (`rude`, `no_answer`, …).
   * Yorliqlar `GET /surveys/red-flags` dan olinadi — qo'lda ko'chirilmaydi,
   * shunda serverda yangi mezon qo'shilsa frontend deploysiz ko'rinadi.
   */
  red_flags?: string[] | null
}

export interface SurveyFeedback {
  /** `ready=false` bo'lsa `null` — soxta raqam ko'rsatilmaydi */
  average: number | null
  count: number
  /** `count` sozlamadagi chegaradan kam bo'lsa `false` */
  ready: boolean
  /**
   * Chegaraning o'zi (`survey.min_responses`). Backend uni qo'shguncha
   * yo'q bo'lishi mumkin — shuning uchun ixtiyoriy va `ratingProgress()`
   * orqali o'qiladi.
   */
  min_responses?: number | null
  /** "1".."5" → javoblar soni */
  distribution: Record<string, number>
  response_rate: number | null
  items: SurveyFeedbackItem[]
}

/**
 * `interface` emas, `type` — TypeScript faqat type-alias'ga
 * yashirin index signature beradi, shusiz `api.get` ga uzatib bo'lmaydi.
 */
export type SurveyQuery = {
  agent_id?: string
  days?: number
  limit?: number
  date_from?: string
  date_to?: string
  /** Guruhdan kelgan hudud bo'yicha filtr */
  region?: string
  /**
   * Erkin qidiruv: savdo xodimining ismi yoki hudud nomi bo'yicha.
   * Filtrni backend bajaradi — sahifadagi ro'yxat emas, chunki
   * `count`, `average` va taqsimot ham qidiruvga mos kelishi kerak.
   */
  search?: string
}

export function useSurveyFeedback(query: SurveyQuery, enabled = true) {
  return useQuery({
    queryKey: ['surveys', query],
    queryFn: () => api.get<SurveyFeedback>('/surveys', query),
    enabled,
    // 403 (sozlama yopgan) — qayta so'rashning ma'nosi yo'q
    retry: false,
  })
}

/* ── Qoidabuzarlik registri ──────────────────────────────────
   Yagona manba — backend. Bu yerda ro'yxat SAQLANMAYDI: serverda
   yangi mezon qo'shilsa, u frontend deploysiz paydo bo'lishi kerak. */

export interface RedFlagOption {
  key: string
  label: string
}

export function useRedFlagOptions() {
  return useQuery({
    queryKey: ['surveys', 'red-flags'],
    queryFn: () => api.get<RedFlagOption[]>('/surveys/red-flags'),
    staleTime: 30 * 60 * 1000,
    // Registr — statik ma'lumot; javob bermasa kalitning o'zi ko'rsatiladi
    retry: false,
  })
}

/** Kalit → yorliq. Yorliq hali kelmagan bo'lsa kalitning o'zi qaytadi. */
export function useRedFlagLabels(): (key: string) => string {
  const options = useRedFlagOptions()
  const map = new Map((options.data ?? []).map((item) => [item.key, item.label]))
  return (key: string) => map.get(key) ?? key
}

/** Xatolik ruxsat bilan bog'liqmi (sozlama bo'limni yopgan) */
export function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}
