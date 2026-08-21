import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import { api } from '@/shared/api/client'

/** Qo'ng'iroq turi — ikkitagina.
 *
 *  `internal` — ikkala tomon ham bizning xodimimiz (suhbatdoshning
 *  raqami kompaniya liniyalari ro'yxatida). Transkript olinadi, lekin
 *  savdo rubrikasi qo'llanmaydi.
 *  `sales` — qolgan hammasi, ya'ni tashqariga chiqqan suhbat.
 *
 *  ⚠️ Tur MAZMUNDAN emas, RAQAMDAN aniqlanadi. Ilgari buni AI
 *  transkriptga qarab qilardi va yanglishardi: eski mijoz ham «qoldiq
 *  qancha» deb qisqa gaplashadi va bu hamkasb suhbatidan farq
 *  qilmaydi. */
export type CallType = 'sales' | 'internal'

export type Direction = 'inbound' | 'outbound'

export interface CallListItem {
  id: string
  started_at: string
  duration_sec: number
  status: string
  agent_id: string
  agent_name: string
  agent_color: string
  /** Kim kimga qo'ng'iroq qilgani. Suhbatni butunlay boshqacha
   *  o'qitadi: mijoz o'zi murojaat qilgani va xodim taklif bilan
   *  chiqqani bir xil emas. */
  direction: Direction
  /** `false` — javobsiz. `null` — MoyZvonki bu maydonni bermagan
   *  (ustun paydo bo'lishidan oldingi qatorlar). */
  answered: boolean | null
  /** Katalogdagi mijoz nomi, u bo'lmasa MoyZvonki bergani */
  client_name: string | null
  /** Nom umuman bo'lmaganda ko'rsatiladi — «—» dan foydaliroq */
  client_phone: string | null
  /** FAQAT `sales` baholanadi — `internal` da `score` bo'sh bo'lishi
   *  xato emas, balki kutilgan holat */
  call_type: CallType | null
  score: number | null
  red_flag_count: number
  needs_review: boolean
}

export interface PaginatedCalls {
  items: CallListItem[]
  total: number
  page: number
  page_size: number
}

export interface RedFlag {
  type: string
  /** Rubrikadagi yorliq — BACKEND qo'shadi.
   *
   *  Nega tarjima faylida emas: admin o'zi qoida yaratishi mumkin
   *  (`shaxsiy_raqamga_ogdirish`) va unga tarjima bo'lmaydi. Yorliq
   *  bahoga qo'yilgan rubrika VERSIYASIDAN olinadi, ya'ni qoida nomi
   *  keyin o'zgarsa eski baho o'z nomi bilan qoladi. */
  label?: string
  severity?: string
  timestamp?: string
  quote?: string
}

export interface CallDetail {
  id: string
  started_at: string
  duration_sec: number
  status: string
  direction: string
  agent: { id: string; full_name: string; region: string; color: string }
  /** Katalogdagi mijoz — faqat raqam `clients` da topilgan bo'lsa */
  client: { id: string; name: string; shop_name: string | null } | null
  /** MoyZvonki bergan nom — katalogda mijoz bo'lmaganda ham to'la */
  client_name: string | null
  client_phone: string | null

  call_type: CallType | null
  /** Tur qanday aniqlangani — raqam bilan. Qaror suhbatdoshning
   *  raqamiga tayanadi, ya'ni sabab tekshirib bo'ladigan fakt */
  call_type_reason: string | null
  call_type_confidence: number | null

  transcript: string | null
  score: {
    overall_score: number
    /** Blok ko'rsatkichlari — QO'LLANILGAN mezonlar ichida
     *  hisoblanib, blok maksimumiga keltirilgan. Butunlay taalluqli
     *  bo'lmagan blok bu obyektga umuman kirmaydi. */
    blocks: Record<string, number>
    /** Qaysi mezonlar qo'llanilgani. `null` — eski baho (bu tushuncha
     *  paydo bo'lishidan oldin qo'yilgan).
     *
     *  Qisqa, takroriy buyurtma suhbatida rubrikaning bir qismi
     *  taalluqli bo'lmaydi: eski mijoz «50 ta chiqaring» deydi va
     *  ehtiyojni aniqlash ham, mahsulot taqdimoti ham talab
     *  qilinmaydi. Ball o'sha qo'llanilganlar ichida hisoblanadi. */
    applicability: {
      /** Qo'llanilgan bloklar maksimumi (100 dan) */
      applicable_max: number
      /** Shulardan olingan ball */
      blocks_total: number | null
      /** Taalluqli emas deb belgilangan kriteriyalar (kalitlar) */
      na_criteria: string[]
      /** O'sha kriteriyalarning NOMLARI — ekranda shular ko'rsatiladi.
       *  Menejer «A2» nima ekanini bilmaydi. */
      na_labels: string[]
      /** Suhbat turi: `repeat_order`, `price_check`, ... */
      scenario: string | null
    } | null
    red_flags: RedFlag[]
    outcome_signal: { type: string; confidence: number } | null
    sentiment: string | null
    coaching_note: string | null
    confidence: number
    needs_review: boolean
    model: string
    rubric_version: string
  } | null
}

/** Jadval sarlavhasida saralanadigan ustunlar — backend oq ro'yxati bilan bir xil */
export type SortField = 'date' | 'agent' | 'client' | 'duration' | 'score' | 'status'

export type SortOrder = 'asc' | 'desc'

/** Tur bo'yicha filtr. `CallType` ustiga ikkitasi qo'shiladi:
 *  `unknown` — hali aniqlanmagan, `not_sales` — savdodan boshqa
 *  hammasi (aniqlanmaganlar ham kiradi: hali bilinmagani ularni
 *  savdo qilmaydi). Qiymatlar backend enumi bilan bir xil. */
export type CallTypeFilter = CallType | 'unknown' | 'not_sales'

export interface CallsQuery {
  page?: number
  page_size?: number
  /** Sana oralig'i (ISO). Berilmasa — barcha vaqt. */
  date_from?: string
  date_to?: string
  agent_id?: string
  score_min?: number
  score_max?: number
  needs_review?: boolean
  call_type?: CallTypeFilter
  direction?: Direction
  /** `no` — javobsiz qo'ng'iroqlar. `unknown` — holat noma'lum. */
  answered?: 'yes' | 'no' | 'unknown'
  search?: string
  sort?: SortField
  order?: SortOrder
}

export const useCalls = (query: CallsQuery) =>
  useQuery({
    queryKey: ['calls', query],
    queryFn: () => api.get<PaginatedCalls>('/calls', query as never),
    placeholderData: keepPreviousData,
  })

export const useCall = (callId: string | undefined) =>
  useQuery({
    queryKey: ['call', callId],
    queryFn: () => api.get<CallDetail>(`/calls/${callId}`),
    enabled: Boolean(callId),
  })

/* ── MoyZvonki sinxronizatsiyasi ──────────────────────────────
   Faqat metadata ko'chiriladi: kim, kimga, qachon, qancha va yozuv
   manzili. Audio baytlari bu yerdan o'tmaydi. */

export interface SyncRequest {
  date_from: string
  date_to?: string
  /**
   * MoyZvonki `supervised=1` — API kalit egasi ko'ra oladigan BARCHA
   * xodimlarning qo'ng'iroqlari. Deyarli har doim `true`: `false` da
   * faqat kalit egasining o'z qo'ng'iroqlari keladi.
   *
   * Qaysi xodimlar SAQLANISHINI `agent_ids` belgilaydi.
   */
  supervised: boolean
  /** Faqat shu xodimlarniki saqlanadi. Bo'sh — hammasi */
  agent_ids?: string[]
  max_calls?: number
}

export interface UnmatchedOwner {
  user_id: string | null
  user_account: string | null
  call_count: number
  label: string
}

export interface SyncResult {
  date_from: string
  date_to: string | null
  pages: number
  fetched: number
  created: number
  updated: number
  skipped_no_agent: number
  /** Admin tanlamagan xodimga tegishli — xato emas, filtr natijasi */
  skipped_not_selected?: number
  /** Audiosi yo'q — SAQLANDI, lekin AI bilan baholanmaydi
   *  (javobsiz yoki yozuv muddati o'tgan) */
  skipped_no_recording: number
  truncated: boolean
  unmatched: UnmatchedOwner[]
  message: string
}

/** Sinxronizatsiyada tanlash mumkin bo'lgan sana oralig'i.
 *
 * Chegara backendda bitta konstanta bilan belgilangan va shu endpoint
 * orqali beriladi. Uni frontendga ko'chirib yozmaymiz: o'shanda raqam
 * ikki joyda turardi va backend so'rovni qisqartirganda tanlagich
 * boshqa chegarani ko'rsatib turardi. */
export interface SyncWindow {
  /** Tanlash mumkin bo'lgan eng eski kun (ISO) */
  earliest: string
  /** Bugundan necha kun orqaga */
  days: number
  /** Audio taxminan shuncha kun saqlanadi.
   *
   * Chegara EMAS: undan eski qo'ng'iroqlar ham to'liq saqlanadi
   * (ro'yxat, faollik, statistika), lekin audiosi bo'lmagani uchun
   * AI bilan baholanmaydi. UI shuni oldindan aytadi. */
  audio_days: number
}

export const useSyncWindow = (enabled = true) =>
  useQuery({
    queryKey: ['calls', 'sync-window'],
    queryFn: () => api.get<SyncWindow>('/calls/sync/window'),
    enabled,
    // Javob — hisoblangan konstanta, so'rov yo'q. Yarim tunda kun
    // almashadi, shuning uchun cheksiz emas
    staleTime: 30 * 60_000,
  })

export function useSyncCalls() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: SyncRequest) => api.post<SyncResult>('/calls/sync', payload),
    onSuccess: () => {
      // Ro'yxat ham, dashboard raqamlari ham yangilanishi kerak
      queryClient.invalidateQueries({ queryKey: ['calls'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}
