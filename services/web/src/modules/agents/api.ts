import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError, BASE_URL, tokenStore } from '@/shared/api/client'

export interface Agent {
  id: string
  full_name: string
  /**
   * Xodim YASHAYDIGAN hudud — tahrirlash formasidagi maydon.
   *
   * ⚠️ Ekranlarda buni ko'rsatmang: u xodim xizmat ko'rsatadigan
   * hudud EMAS. Toshkentda yashab Samarqand mijozlarini yuritish
   * mumkin — o'shanda profil «Toshkent» deb turadi, Telegram
   * guruhlari bo'limi esa o'sha xodimni «Samarqand» da ko'rsatadi.
   */
  region: string
  /**
   * Xodim XIZMAT KO'RSATADIGAN hududlar — biriktirilgan faol
   * guruhlaridan yig'iladi. Guruhlar daraxti bilan bir xil manba,
   * shuning uchun ikkala ekranda bir xil ro'yxat ko'rinadi.
   *
   * Ixtiyoriy: eski backend bu maydonni qaytarmaydi.
   */
  regions?: string[]
  phone: string | null
  external_id: string | null
  hired_at: string | null
  is_active: boolean
  color: string
  avatar_url: string | null
  /**
   * Shu xodimga hozir biriktirilgan Telegram guruhlari soni.
   *
   * ATAYIN ixtiyoriy: eski backend bu maydonni qaytarmaydi va o'shanda
   * ogohlantirish umuman chiqmasligi kerak — «0 ta guruh bo'shaydi»
   * degan bo'sh qo'rqitish ogohlantirishning qadrini tushiradi.
   */
  bound_groups?: number
  /**
   * Faqat `PATCH` javobida to'ladi: shu amal natijasida bo'shatilgan
   * guruhlar soni. Boshqa endpointlarda `null`/yo'q.
   */
  freed_groups?: number | null

  /* ── Botga ulanish ───────────────────────────────────────────
     Telegram Bot API a'zoning telefon raqamini KO'RSATMAYDI. Xodim
     botga o'zi «raqamimni yuborish» tugmasi orqali yuborgandagina
     uning `telegram_user_id` si ma'lum bo'ladi — va faqat shundan
     keyin uning guruhlari avtomatik biriktiriladi.

     Uchala maydon ham ATAYIN ixtiyoriy: eski backend ularni
     qaytarmaydi va o'shanda holat umuman ko'rsatilmasligi kerak.
     «Ulanmagan» deb yozib qo'yish — yolg'on ogohlantirish. */
  telegram_user_id?: number | null
  telegram_username?: string | null
  enrolled_at?: string | null

  /** Arxivga o'tgan vaqt. `null`/yo'q — odatdagi xodim.
   *  Arxivlangan xodim ekranlarda ko'rinmaydi, lekin uning
   *  qo'ng'iroqlari va baholari saqlanib qoladi. */
  archived_at?: string | null
}

/** Xodimning botga ulanish holati */
export type Enrollment = 'enrolled' | 'pending' | 'unknown'

/**
 * Holat faqat backend shu maydonlarni qaytarsagina aytiladi.
 *
 * `unknown` — maydon javobda umuman yo'q. Bunday holatda UI hech
 * nima ko'rsatmaydi: mavjud bo'lmagan ma'lumot asosida «xodim
 * ulanmagan» deyish adminni bo'sh ishga yuborardi.
 */
export function enrollmentOf(agent: Agent | null | undefined): Enrollment {
  if (!agent) return 'unknown'
  if (agent.telegram_user_id != null || agent.enrolled_at != null) return 'enrolled'
  if ('telegram_user_id' in agent || 'enrolled_at' in agent) return 'pending'
  return 'unknown'
}

/** Xodim nechta guruhni ushlab turibdi — maydon yo'q bo'lsa 0 */
export function boundGroupCount(agent: Agent | null | undefined): number {
  const value = agent?.bound_groups
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0
}

/** Saqlashdan keyin nechta guruh bo'shatilgani — maydon yo'q bo'lsa 0 */
export function freedGroupCount(agent: Agent | null | undefined): number {
  const value = agent?.freed_groups
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0
}

export interface AgentInput {
  full_name: string
  region: string
  phone?: string | null
  external_id?: string | null
  hired_at?: string | null
  color?: string
  is_active?: boolean
}

export interface FeedbackItem {
  id: string
  agent_id: string
  agent_name: string
  csat: number
  resolution: string | null
  comment: string | null
  responded_at: string
  region: string
}

export interface FeedbackSummary {
  average: number | null
  count: number
  ready: boolean
  /**
   * O'rtacha ochilishi uchun kerakli javoblar soni (`survey.min_responses`).
   * Ixtiyoriy: backend hali qaytarmasligi mumkin — `ratingProgress()`
   * shu holatni o'zi hal qiladi.
   */
  min_responses?: number | null
  distribution: Record<string, number>
  response_rate: number | null
  items: FeedbackItem[]
}

export interface AgentsQuery {
  includeInactive?: boolean
  /** Arxivlanganlarni ham ko'rsatish */
  includeArchived?: boolean
  /** Ism yoki hudud bo'yicha — filtrni backend bajaradi, ro'yxat emas */
  search?: string
}

/**
 * Xodimlar ro'yxati.
 *
 * Eski chaqiruvlar buzilmasin uchun `boolean` ham qabul qilinadi
 * (`useAgents(true)` — faol emaslar bilan birga).
 */
export const useAgents = (options: boolean | AgentsQuery = false) => {
  const {
    includeInactive = false,
    includeArchived = false,
    search,
  } = typeof options === 'boolean'
    ? { includeInactive: options, includeArchived: false, search: undefined }
    : options
  // Bo'sh qidiruv umuman yuborilmaydi — `?search=` kesh kalitini
  // ikkiga bo'lib, bir xil ro'yxatni ikki marta tortib olardi
  const needle = search?.trim() || undefined

  return useQuery({
    queryKey: ['agents', { includeInactive, includeArchived, search: needle ?? null }],
    queryFn: () =>
      api.get<Agent[]>('/agents', {
        include_inactive: includeInactive,
        include_archived: includeArchived,
        search: needle,
      }),
  })
}

export const useAgent = (agentId: string | undefined) =>
  useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => api.get<Agent>(`/agents/${agentId}`),
    enabled: Boolean(agentId),
  })

/**
 * Client baholari xulosasi.
 *
 * ⚠️ `date_from`/`date_to` — ULAR USTUN. Ilgari bu hook faqat `days`
 * («oxirgi N kun») yuborardi, sahifaning qolgan qismi esa tanlangan
 * ANIQ oraliqni. Preset «o'tgan oy» bo'lganda ikkisi butunlay boshqa
 * oynaga tushardi: KPI «0 qo'ng'iroq» deb turgan iyul oyida client
 * bahosi 3.8 bo'lib ko'rinardi — u avgust ma'lumoti edi.
 *
 * `days` zaxira bo'lib qoladi: oraliq berilmagan chaqiruvchilar
 * (masalan xodimlar ro'yxatidagi qisqa xulosa) avvalgidek ishlaydi.
 */
export const useFeedback = (params: {
  agent_id?: string
  days?: number
  date_from?: string
  date_to?: string
  limit?: number
  enabled?: boolean
}) =>
  useQuery({
    queryKey: ['feedback', params],
    queryFn: () =>
      api.get<FeedbackSummary>('/surveys', {
        agent_id: params.agent_id,
        days: params.days ?? 90,
        date_from: params.date_from,
        date_to: params.date_to,
        limit: params.limit ?? 50,
      }),
    enabled: params.enabled !== false,
  })

export function useSaveAgent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: AgentInput & { id?: string }) =>
      id ? api.patch<Agent>(`/agents/${id}`, body) : api.post<Agent>('/agents', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
      /* Faolsizlantirish xodimning guruhlarini bo'shatadi va ularning
         navbatdagi so'rovnomalarini bekor qiladi — Guruhlar sahifasi
         eski holatni ko'rsatib turmasin */
      queryClient.invalidateQueries({ queryKey: ['groups'] })
      queryClient.invalidateQueries({ queryKey: ['surveys'] })
    },
  })
}


/* ── MoyZvonki'dan HAMMASINI olish (faqat admin) ──────────────
   Bitta tugma: MoyZvonki'dagi barcha xodim tizimga tushadi.
   MAVJUDLARGA TEGILMAYDI — faqat yetishmayotgani yaratiladi,
   shuning uchun tugmani necha marta bosish xavfsiz. */

export interface ImportAllResult {
  total: number
  created: number
  /** Ismi bo'yicha topilib, `external_id` si to'ldirilganlar */
  linked: number
  /** Allaqachon bor edi — tegilmadi */
  skipped: number
  created_names: string[]
  message: string
}

export function useImportAllAgents() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (options?: { region?: string; detectPhones?: boolean }) =>
      api.post<ImportAllResult>('/agents/moizvonki/import-all', {
        ...(options?.region ? { region: options.region } : {}),
        detect_phones: options?.detectPhones !== false,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}

/* ── O'chirish (faqat admin) ──────────────────────────────────
   MoyZvonki'dan barcha xodim tortiladi, ortiqchasi keyin o'chiriladi.
   Amal QAYTARIB BO'LMAYDI: xodim bilan birga uning qo'ng'iroqlari va
   baholari ham ketadi. Shuning uchun avval `impact` so'raladi. */

export interface DeletionImpact {
  agent_id: string
  full_name: string
  calls: number
  scores: number
  surveys: number
  survey_responses: number
  groups: number
  clients: number
  users: number
  /** `true` — bog'liq ma'lumoti yo'q, qatori butunlay o'chadi.
   *  `false` — arxivga o'tadi, ma'lumoti saqlanadi. */
  safe: boolean
  /** Nega arxivga o'tishi — o'zbekcha */
  blockers: string[]
}

export interface DeleteAgentsResult {
  /** Qatori butunlay o'chirildi — saqlanadigan narsa yo'q edi */
  deleted: string[]
  /** Ekranlardan olib tashlandi, MA'LUMOTI SAQLANDI */
  archived: DeletionImpact[]
  kept_calls: number
  kept_surveys: number
  message: string
}

export function useDeletionImpact() {
  return useMutation({
    mutationFn: (agentIds: string[]) =>
      api.post<DeletionImpact[]>('/agents/deletion-impact', {
        agent_ids: agentIds,
      }),
  })
}

export function useDeleteAgents() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (agentIds: string[]) =>
      api.post<DeleteAgentsResult>('/agents/delete', { agent_ids: agentIds }),
    onSuccess: () => {
      // Xodim o'chsa qo'ng'iroqlari, baholari va guruh biriktirishlari
      // ham o'zgaradi — hamma bog'liq ekran yangilansin
      for (const key of ['agents', 'agent', 'analytics', 'groups', 'surveys', 'calls'])
        queryClient.invalidateQueries({ queryKey: [key] })
    },
  })
}

export function useRestoreAgents() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (agentIds: string[]) =>
      api.post<DeleteAgentsResult>('/agents/restore', { agent_ids: agentIds }),
    onSuccess: () => {
      for (const key of ['agents', 'agent', 'analytics', 'groups'])
        queryClient.invalidateQueries({ queryKey: [key] })
    },
  })
}

/* ── Profil rasmi ────────────────────────────────────────── */

export function useUploadAvatar() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ agentId, file }: { agentId: string; file: File }) => {
      const body = new FormData()
      body.append('file', file)
      // FormData bo'lgani uchun api.post ishlamaydi — Content-Type ni
      // brauzer o'zi (boundary bilan) qo'yishi kerak
      const token = tokenStore.get()
      const response = await fetch(`${BASE_URL}/api/v1/agents/${agentId}/avatar`, {
        method: 'POST',
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body,
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new ApiError(
          response.status,
          data?.error?.code ?? 'upload_failed',
          data?.error?.message ?? 'Rasm yuklanmadi',
        )
      }
      return (await response.json()) as Agent
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent'] })
    },
  })
}

export function useDeleteAvatar() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (agentId: string) => api.delete<Agent>(`/agents/${agentId}/avatar`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent'] })
    },
  })
}
