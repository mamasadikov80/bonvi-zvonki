/**
 * Mijozlar — qo'ng'iroqlardan yig'ilgan ro'yxat.
 *
 * Mijoz bizda alohida yozuv EMAS: `clients` katalogi bo'sh va u boshqa
 * vazifa uchun (Telegram so'rovnomasi). Bu yerdagi «mijoz» — telefon
 * RAQAMI va u bilan bo'lgan barcha suhbatlar; kalit — raqamning oxirgi
 * 9 tasi, chunki bir odam turli formatda kelishi mumkin.
 * Sababi to'liq: `clients/application/directory.py`.
 */

import { useQuery } from '@tanstack/react-query'

import type { CallType } from '@/modules/calls/api'
import type {
  SaleReviewStatus,
  SaleRule,
  SaleSkipReason,
  SaleVerdict,
} from '@/modules/sales/api'
import { api } from '@/shared/api/client'

/** Kim ro'yxatga kiradi. `clients` — ichki suhbatlardan boshqa hammasi */
export type ClientScope = 'clients' | 'internal' | 'all'

export type ClientSort = 'last_call' | 'calls' | 'missed' | 'talk' | 'score' | 'name'
export type SortOrder = 'asc' | 'desc'

export interface ClientRow {
  /** Raqamning oxirgi 9 tasi — manzilda ham shu ishlatiladi */
  key: string
  name: string | null
  phone: string | null
  calls_total: number
  inbound: number
  outbound: number
  /** Kiruvchi va javobsiz — kompaniya javob bermagani */
  missed: number
  talk_seconds: number
  /** `null` — kartochkada tanlangan davrda aloqa bo'lmagan */
  first_call_at: string | null
  last_call_at: string | null
  /** Nechta xodim gaplashgan */
  agent_count: number
  /** Eng ko'p gaplashgan xodim */
  main_agent_id: string | null
  main_agent_name: string | null
  main_agent_color: string | null
  avg_score: number | null
  /** Nechta suhbat baholangan — o'rtacha shundan */
  scored: number
}

export interface PaginatedClients {
  items: ClientRow[]
  total: number
  page: number
  page_size: number
}

export interface ClientsQuery {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
  agent_ids?: string[]
  regions?: string[]
  scope?: ClientScope
  search?: string
  sort?: ClientSort
  order?: SortOrder
}

export const useClients = (query: ClientsQuery) =>
  useQuery({
    queryKey: ['clients', query],
    queryFn: () => api.get<PaginatedClients>('/clients', query as never),
    staleTime: 60_000,
  })

export interface ClientAgent {
  agent_id: string
  full_name: string
  color: string | null
  region: string | null
  calls: number
  last_call_at: string
}

export interface ClientDetail {
  client: ClientRow
  /** Mijoz bilan gaplashgan xodimlar — ko'pdan kamga */
  agents: ClientAgent[]
}

/** Kartochkadagi davr. Bo'sh — butun tarix. */
export interface ClientPeriod {
  date_from?: string
  date_to?: string
}

/**
 * Bitta mijoz. Davr berilmasa — butun tarix.
 *
 * ⚠️ Tanlangan davrda aloqa bo'lmasa ham javob KELADI: sonlari nol,
 * sanalari bo'sh. «Mijoz topilmadi» degan xato faqat raqam umuman
 * bo'lmaganda chiqadi — davrni toraytirish mijozni yo'qotmaydi.
 */
export const useClient = (key: string | undefined, period: ClientPeriod = {}) =>
  useQuery({
    queryKey: ['clients', 'detail', key, period],
    queryFn: () => api.get<ClientDetail>(`/clients/${key}`, period as never),
    enabled: Boolean(key),
  })

export interface ClientCall {
  id: string
  started_at: string
  duration_sec: number
  direction: 'inbound' | 'outbound'
  answered: boolean | null
  status: string
  /** `sales` | `internal`. Qo'ng'iroqlar bo'limi bilan bir xil tur:
   *  yorliq (`CallTypeBadge`) ikkala joyda ham shu qiymatga tayanadi */
  call_type: CallType | null
  agent_id: string
  agent_name: string
  agent_color: string | null
  score: number | null
  red_flag_count: number
  needs_review: boolean
}

export interface PaginatedClientCalls {
  items: ClientCall[]
  total: number
  page: number
  page_size: number
}

export const useClientCalls = (
  key: string | undefined,
  query: ClientPeriod & { page?: number; page_size?: number } = {},
  { enabled = true }: { enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: ['clients', 'calls', key, query],
    queryFn: () =>
      api.get<PaginatedClientCalls>(`/clients/${key}/calls`, query as never),
    enabled: Boolean(key) && enabled,
  })

/* ── Savdo tarixi (savdo nazorati, 3-bosqich) ────────────────
 *
 * ⚠️ TURLAR SAVDO MODULIDAN OLINADI, nusxa ko'chirilmaydi. Savdo
 * qatori ikkala ekranda ham bir xil o'qiladi (yorliqlar
 * `sales/badges.tsx` dan keladi), ya'ni ikkita lug'at bo'lsa ular
 * albatta bir-biridan uzoqlashardi.
 */

export interface ClientSale {
  id: string
  /** `YYYY-MM-DD` — ⚠️ VAQTI YO'Q. SAP savdoga soat bermaydi */
  occurred_on: string
  /** SAP dagi `Номер операции` — qatorni SAP da topish uchun */
  external_id: string
  branch: string | null
  direction: string | null
  agent_id: string | null
  agent_name: string | null
  amount: number | null
  currency: string
  amount_usd: number | null
  verdict: SaleVerdict
  broken_rules: SaleRule[]
  skip_reason: SaleSkipReason | null

  /* ── Dalil ────────────────────────────────────────────────
   * ⚠️ Nazorat ro'yxatidagi (`ComplianceRow`) qiymatlar bilan AYNAN
   * bir xil: ikkala ekran ham bitta manbadan oziqlanadi. Xulosani
   * ko'rsatib, uni tekshirish imkonini bermaslik mumkin emas —
   * «toza» yorlig'i yonida «oxirgi suhbat qachon bo'lgan» turishi
   * kerak, aks holda rahbar boshqa ekranga o'tib qidirardi. */

  /** Savdodan OLDINGI (yoki savdo kunidagi) eng yaqin suhbat */
  last_call_at: string | null
  last_call_agent: string | null
  /** Savdodan necha kun oldin. `0` — o'sha kuni */
  days_before: number | null
  /** R2: shu mijozning oldingi savdosi. `null` — birinchi savdo */
  previous_sale_on: string | null
  calls_between: number
  calls_total: number

  /** `null` — rahbar hali qaror qo'ymagan */
  review_status: SaleReviewStatus | null
}

export interface ClientSales {
  items: ClientSale[]
  /** Davrdagi BARCHA savdolar — `items` chegaraga urilsa ham to'g'ri */
  total: number
  amount_usd: number
  suspicious: number
  not_checkable: number
  /** R1 oynasi (`sales.window_days`) — izohda ochiq yoziladi */
  window_days: number
}

/**
 * Mijozning savdolari.
 *
 * ⚠️ RUXSAT — `sales:read`, kartochkani ochish huquqidan ALOHIDA.
 * Savdo xodimi mijozini ko'radi, uning ustidan olib borilayotgan
 * tekshiruvni esa YO'Q. Shuning uchun so'rov `enabled` bilan
 * to'xtatiladi: ruxsatsiz odam sahifani ochganda 403 xatosi ham,
 * bo'sh joy ham ko'rinmasligi kerak.
 *
 * Davr — qo'ng'iroqlarnikidek `date_from`/`date_to`: kartochkadagi
 * ikkala ro'yxat BIR XIL oynani ko'rishi shart.
 */
export const useClientSales = (
  key: string | undefined,
  period: ClientPeriod = {},
  { enabled = true }: { enabled?: boolean } = {},
) =>
  useQuery({
    queryKey: ['clients', 'sales', key, period],
    queryFn: () => api.get<ClientSales>(`/clients/${key}/sales`, period as never),
    enabled: Boolean(key) && enabled,
    // Xulosa bazada saqlanmaydi — har so'rovda qaytadan hisoblanadi
    // va yangi qo'ng'iroq sinxronlanishi bilan o'zgarishi mumkin.
    staleTime: 30_000,
  })
