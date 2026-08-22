/**
 * Savdo nazorati — API qatlami.
 *
 * Shartnoma: `docs/savdo-nazorati.md`, 7.1-bo'lim. Maydon nomlari
 * AYNAN o'sha yerdan olingan — bu yerda «qulayroq» nom o'ylab
 * topilmaydi, aks holda backend bilan ikkita lug'at paydo bo'lardi.
 *
 * ⚠️ ENG MUHIM NOZIK JOY: xulosa (`verdict`) bazada SAQLANMAYDI, u
 * har so'rovda qaytadan hisoblanadi. Sabab shartnomaning 3-bo'limida:
 * qo'ng'iroq savdodan KEYIN sinxronlanishi mumkin va o'shanda yozib
 * qo'yilgan «shubhali» belgisi yolg'onga aylanardi. Frontend uchun
 * buning oqibati aniq — natijani uzoq keshlab bo'lmaydi va qaror
 * qo'yilgach ro'yxat qaytadan so'raladi.
 *
 * Sanalar: `date_from`/`date_to` — `YYYY-MM-DD`, VAQTSIZ. Savdoda
 * vaqt yo'q (`sales.occurred_on` — `date`), shuning uchun ilovadagi
 * `rangeToQuery` (ISO datetime) bu yerda ISHLATILMAYDI: backend
 * parametrni `date` deb o'qiydi va `…T00:00:00.000Z` ni rad etardi.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, postForm } from '@/shared/api/client'

/* ── Turlar ──────────────────────────────────────────────── */

/** Uch toifa. `not_checkable` — shubhali EMAS, tekshirib bo'lmaydi */
export type SaleVerdict = 'ok' | 'suspicious' | 'not_checkable'

/** Nega tekshirib bo'lmadi: umumiy kod yoki ishonchsiz telefon */
export type SaleSkipReason = 'generic_code' | 'no_phone'

/** Qoidalar. R1 — savdo oldidan suhbat yo'q, R2 — ikki savdo
 *  orasida suhbat yo'q, R3 — butun tarixda umuman suhbat yo'q */
export type SaleRule = 'R1' | 'R2' | 'R3'

export const SALE_RULES: SaleRule[] = ['R1', 'R2', 'R3']

/** Rahbarning qarori — bazada saqlanadigan YAGONA narsa */
export type SaleReviewStatus = 'justified' | 'confirmed'

/** «Oqlandi» qarorining sababi */
export type SaleReviewReason = 'walk_in' | 'telegram' | 'visit' | 'contract' | 'other'

export const REVIEW_REASONS: SaleReviewReason[] = [
  'walk_in',
  'telegram',
  'visit',
  'contract',
  'other',
]

/**
 * Ro'yxat filtridagi qaror holati.
 *
 * ⚠️ «Hammasi» — ANIQ QIYMAT (`all`), parametrni yubormaslik EMAS.
 * Backendda sukut qiymat `new`, ya'ni bo'sh so'rov «hammasi» degani
 * emas, «ko'rilmaganlar» degani. Shuning uchun tanlov har doim ochiq
 * yuboriladi; aks holda ekrandagi yorliq yolg'on gapirardi —
 * «Hammasi» deb turib faqat ko'rilmaganlar chiqardi.
 */
export type SaleReviewFilter = 'new' | 'all' | SaleReviewStatus

/** Tanlagichdagi tartib: avval navbat, keyin arxiv, oxirida hammasi */
export const REVIEW_STATES: SaleReviewFilter[] = [
  'new',
  'justified',
  'confirmed',
  'all',
]

/**
 * Saralanadigan ustunlar — backenddagi `ComplianceSort` ning aynan
 * nusxasi.
 *
 * ⚠️ `verdict` bo'yicha saralash YO'Q: backend uni qabul qilmaydi
 * (422). Toifa bo'yicha ajratish uchun yuqoridagi uchta kartochka
 * bor va u aniqroq ishlaydi — saralash toifalarni aralashtirib
 * ko'rsatardi.
 */
export type SaleSort = 'date' | 'amount' | 'agent' | 'partner'
export type SortOrder = 'asc' | 'desc'

export interface SaleReview {
  status: SaleReviewStatus
  reason: SaleReviewReason | null
  note: string | null
  /** Kim qaror qildi — ismi (uuid emas) */
  reviewed_by: string | null
  reviewed_at: string | null
}

/**
 * `/sales/compliance` dagi bitta qator.
 *
 * Dalil maydonlari (`last_call_*`, `days_before`, `previous_sale_on`,
 * `calls_between`, `calls_total`) — ekranning eng qimmat qismi:
 * rahbar sonni qo'lda qayta hisoblab tekshiradi. Ular hech qayerda
 * qisqartirilmaydi va Excelga ham to'liq tushadi.
 */
export interface ComplianceRow {
  id: string
  /** `YYYY-MM-DD` — vaqti YO'Q, faqat sana */
  occurred_on: string
  /** SAP dagi `Номер операции` — qatorni SAP da topish uchun */
  external_id: string
  partner_code: string
  /** ⚠️ Bo'sh bo'lishi mumkin: eksportda nomi yo'q qatorlar uchraydi */
  partner_name: string | null
  phone: string | null
  phone_key: string | null
  branch: string | null
  direction: string | null
  agent_id: string | null
  agent_name: string | null
  /** Hujjat valyutasidagi summa. `null` — SAP da katak bo'sh edi */
  amount: number | null
  currency: string
  /** Aynan shu summa dollarda — taqqoslash faqat shu ustunda ma'noli */
  amount_usd: number | null
  verdict: SaleVerdict
  broken_rules: SaleRule[]
  skip_reason: SaleSkipReason | null
  /** Savdodan OLDINGI eng yaqin suhbat */
  last_call_at: string | null
  last_call_agent: string | null
  days_before: number | null
  /** R2: shu mijozning oldingi savdosi */
  previous_sale_on: string | null
  /** R2: ikki savdo orasidagi suhbatlar */
  calls_between: number
  /** R3: butun tarixdagi suhbatlar */
  calls_total: number
  review: SaleReview | null
}

export interface CompliancePage {
  items: ComplianceRow[]
  total: number
  page: number
  page_size: number
  /**
   * Qo'ng'iroq qidiriladigan oyna (`sales.window_days` sozlamasi).
   *
   * Javob bilan birga keladi va ekranda ochiq yoziladi: sozlama
   * o'zgarsa ekrandagi izoh ham o'zi o'zgaradi. Sonni frontendga
   * ko'chirib yozish ikkita haqiqat tug'dirardi.
   */
  window_days: number
}

export interface ComplianceQuery {
  page?: number
  page_size?: number
  /** `YYYY-MM-DD` — vaqtsiz (backend `date` deb o'qiydi) */
  date_from?: string
  date_to?: string
  agent_ids?: string[]
  branches?: string[]
  verdict?: SaleVerdict
  review?: SaleReviewFilter
  rule?: SaleRule
  /** Mijoz nomi, kodi yoki telefoni */
  search?: string
  sort?: SaleSort
  order?: SortOrder
}

/** Xodimlar kesimi — «kimda oqlanmagan savdo ko'p» */
export interface ComplianceAgentRow {
  agent_id: string | null
  /** `null` — filiali xodimga biriktirilmagan savdolar */
  agent_name: string | null
  sales: number
  ok: number
  suspicious: number
  not_checkable: number
  /** Ko'rilmaganlar — tekshiruv navbatining uzunligi */
  new: number
  justified: number
  confirmed: number
}

/**
 * Toifalar bo'yicha sonlar.
 *
 * Uchala toifa ham EKRANDA turadi — bu shartnomaning talabi
 * (4-bo'lim): `not_checkable` yashirilsa, ro'yxat «hammasi joyida»
 * degan yolg'on taassurot berardi, holbuki u SAP dagi ma'lumot
 * sifatining ko'rsatkichi.
 */
export interface ComplianceSummary {
  total: number
  ok: number
  suspicious: number
  not_checkable: number
  /** Qaror kesimi: ko'rilmagan / oqlangan / tasdiqlangan */
  new: number
  justified: number
  confirmed: number
  window_days: number
  agents: ComplianceAgentRow[]
}

/** Filial → xodim xaritasining bitta qatori */
export interface SaleBranch {
  /** SAP dagi nom — kalit ham, ko'rsatiladigan matn ham shu */
  branch: string
  agent_id: string | null
  agent_name: string | null
  /** Nom bo'yicha o'zi topilganmi yoki rahbar qo'lda qo'yganmi */
  matched_automatically: boolean
  /** Shu filialdagi savdolar soni — dalil: qaysi filial muhimroq */
  sales: number
}

/** Import: fayl turi sarlavha bo'yicha aniqlanadi */
export type SalesFileKind = 'register' | 'catalog' | 'balance'

/**
 * Import hisoboti — backenddagi `ImportReport` ning aynan nusxasi.
 *
 * Har son ALOHIDA savolga javob beradi va ular qo'shilmaydi:
 * `read` — fayldan o'qilgani, `created`/`updated` — bazaga tushgani,
 * qolganlari — nuqsonlar.
 */
export interface SalesImportReport {
  kind: SalesFileKind
  source: string
  read: number
  created: number
  updated: number
  /** Kod yoki sana yo'qligi uchun yozilmagan qatorlar */
  skipped: number
  /** Kodi katalogda topilmagan — savdo saqlanadi, lekin telefonsiz */
  unknown_partner: number
  /** SAP da tanilmagan `Тип` — `other` bo'lib saqlanadi */
  unknown_op_type: number
  phones_filled: number
  /** Katalog kelgach tiklangan bog'lanishlar */
  linked_sales: number
  /** Xodimga biriktirilmagan filiallar — NOMLARI bilan */
  unmatched_branches: string[]
}

/* ── O'qish ──────────────────────────────────────────────── */

/**
 * Ro'yxat.
 *
 * `staleTime` qisqa: xulosa har so'rovda qaytadan hisoblanadi va
 * yangi qo'ng'iroq sinxronlanishi bilan o'zgarishi mumkin.
 */
export const useCompliance = (query: ComplianceQuery) =>
  useQuery({
    queryKey: ['sales', 'compliance', query],
    queryFn: () => api.get<CompliancePage>('/sales/compliance', query as never),
    staleTime: 30_000,
  })

/**
 * Toifalar soni.
 *
 * ⚠️ Sahifalash va saralash YUBORILMAYDI: sonlar butun tanlov
 * bo'yicha, ko'rilayotgan sahifa bo'yicha emas. Aks holda «20 ta
 * shubhali» degan son sahifadan sahifaga o'zgarib turardi.
 *
 * ⚠️ `verdict`, `rule`, `review` ham yuborilmaydi va backend ularni
 * umuman qabul qilmaydi. Sabab: hisobot ro'yxat filtriga ergashsa,
 * «Shubhalilar» tanlanganda qolgan ikkala son nolga tushardi — ya'ni
 * tanlov o'z asosini o'chirib qo'yardi va kartochkalar tugma sifatida
 * ishlamasdi.
 */
export const useComplianceSummary = (query: ComplianceQuery) => {
  const {
    page: _page,
    page_size: _size,
    sort: _sort,
    order: _order,
    verdict: _verdict,
    rule: _rule,
    review: _review,
    ...filter
  } = query
  return useQuery({
    queryKey: ['sales', 'summary', filter],
    queryFn: () =>
      api.get<ComplianceSummary>('/sales/compliance/summary', filter as never),
    staleTime: 30_000,
  })
}

/** Filial → xodim xaritasi */
export const useSaleBranches = () =>
  useQuery({
    queryKey: ['sales', 'branches'],
    queryFn: () => api.get<SaleBranch[]>('/sales/branches'),
    staleTime: 5 * 60 * 1000,
  })

/**
 * Excel uchun BARCHA qatorlarni yig'adi.
 *
 * NEGA ALOHIDA SO'ROV. Ekranda 20–50 qator turadi, faylga esa
 * ekrandagi FILTR bo'yicha hammasi tushishi kerak: rahbar faylni
 * ochib sonni qayta hisoblaydi va 3-sahifadagi savdo yo'qolgan
 * fayl bu ishni imkonsiz qiladi.
 *
 * Sahifalab olinadi va bu majburiy: backendda `page_size` ning
 * chegarasi 200 (`Query(le=200)`), ya'ni «hammasini bitta so'rovda»
 * degan yechim 422 bilan tugardi. Yig'ish javobdagi qatorlar soniga
 * qarab to'xtaydi — chegara o'zgarsa ham kod ishlashda qoladi.
 */
export async function fetchAllCompliance(
  query: ComplianceQuery,
  { batch = 200, maxRows = 20_000 }: { batch?: number; maxRows?: number } = {},
): Promise<{ rows: ComplianceRow[]; total: number; truncated: boolean }> {
  const rows: ComplianceRow[] = []
  let page = 1
  let total = 0

  for (;;) {
    const chunk = await api.get<CompliancePage>('/sales/compliance', {
      ...query,
      page,
      page_size: batch,
    } as never)
    total = chunk.total
    rows.push(...chunk.items)

    // Bo'sh javob — oxiri (yoki backend sahifani tushunmadi):
    // ikkala holatda ham davom etish cheksiz sikl bo'lardi
    if (!chunk.items.length) break
    if (rows.length >= total || rows.length >= maxRows) break
    page += 1
  }

  return { rows, total, truncated: rows.length < total }
}

/* ── Yozish ──────────────────────────────────────────────── */

/**
 * Savdo nazorati bilan bog'liq hamma narsa eskiradi.
 *
 * Qaror ro'yxatga ham, toifalar soniga ham ta'sir qiladi (ro'yxat
 * sukut bo'yicha faqat KO'RILMAGANLARNI ko'rsatadi — qaror qo'yilgan
 * qator o'sha zahoti ro'yxatdan chiqib ketishi kerak).
 */
function useInvalidateSales() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['sales'] })
}

export interface ReviewInput {
  saleId: string
  status: SaleReviewStatus
  reason?: SaleReviewReason | null
  note?: string | null
}

export function useReviewSale() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: ({ saleId, ...body }: ReviewInput) =>
      api.post<SaleReview>(`/sales/${saleId}/review`, body),
    onSuccess: invalidate,
  })
}

/**
 * Filialga xodim biriktirish.
 *
 * ⚠️ Filial nomi manzilning BIR QISMI va u kirill harflar, probel va
 * nuqta bilan keladi («Кукон метан булими»). `encodeURIComponent`siz
 * so'rov manzili buzilardi.
 *
 * `agent_id: null` — bog'lanishni uzish. Bu ham to'liq huquqli
 * tanlov: `Зухриддин` ATAYLAB xodimsiz qoladi (shartnoma, 4-bo'lim).
 */
export function useAssignBranch() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: ({ branch, agentId }: { branch: string; agentId: string | null }) =>
      api.put<SaleBranch>(`/sales/branches/${encodeURIComponent(branch)}`, {
        agent_id: agentId,
      }),
    onSuccess: invalidate,
  })
}

/**
 * Excel yuklash.
 *
 * Fayl turi (registr / katalog / balans) SARLAVHA bo'yicha backendda
 * aniqlanadi — bu yerda tanlov ham, taxmin ham yo'q.
 */
export function useImportSales() {
  const invalidate = useInvalidateSales()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return postForm<SalesImportReport>('/sales/import', form)
    },
    onSuccess: invalidate,
  })
}
