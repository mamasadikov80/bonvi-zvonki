/**
 * Hududlar — API qatlami.
 *
 * Yagona haqiqat manbai `GET /regions`. Kodda QAT'IY viloyatlar
 * ro'yxati yo'q va bo'lmaydi: Bonvi bitta viloyatni bir nechta
 * alohida hududga bo'ladi («Samarqand shimol», «Samarqand janub»),
 * shuning uchun ro'yxatni faqat admin belgilaydi.
 *
 * Muhim nozik joy: hudud `agents`, `clients`, `telegram_groups` da
 * MATN bo'lib saqlanadi (FK emas). Shuning uchun:
 *   • nom o'zgarsa — backend uchala jadvalni bitta tranzaksiyada
 *     kaskad yangilaydi va nechta qator tegilganini qaytaradi;
 *   • ishlatilayotgan hududni o'chirish 409 bilan rad etiladi.
 * UI ikkalasini ham ochiq ko'rsatadi — bu yerda nomni o'zgartirish
 * kosmetik tahrir emas.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import { api, ApiError } from '@/shared/api/client'

/* ── Turlar (shartnoma bo'yicha) ─────────────────────────── */

export interface RegionUsage {
  agents: number
  clients: number
  groups: number
}

export interface Region {
  id: string
  name: string
  is_active: boolean
  sort_order: number
  note: string | null
  /** Qayerda ishlatilmoqda — o'chirishdan oldingi oqibat */
  usage: RegionUsage
}

/** PATCH javobi: nom o'zgargan bo'lsa nechta qator yangilangani */
export interface SavedRegion extends Region {
  renamed?: RegionUsage
  /** Arxivlashda hududi olib tashlangan faol guruhlar soni */
  detached_groups?: number
}

export interface RegionInput {
  name?: string
  is_active?: boolean
  sort_order?: number
  note?: string | null
  /**
   * Arxivlashda hududni FAOL guruhlardan uzsinmi?
   *
   * Standart `false`: uzilgan guruh so'rovnoma olishni to'xtatadi,
   * shuning uchun bu tugmachani bosishning yon ta'siri bo'lmasligi
   * kerak — admin ongli ravishda belgilaydi.
   *
   * Tarixga ta'sir qilmaydi: har so'rovnoma o'z hudud nusxasini
   * saqlaydi, o'tgan oylar hisoboti o'zgarmaydi.
   */
  detach_groups?: boolean
}

/** Arxivlashdan oldin: nechta faol guruh uziladi */
export interface ArchivePreview {
  region: string
  active_groups: number
}

/* ── Yordamchilar ────────────────────────────────────────── */

export const EMPTY_USAGE: RegionUsage = { agents: 0, clients: 0, groups: 0 }

export function usageTotal(usage: RegionUsage | null | undefined): number {
  if (!usage) return 0
  return usage.agents + usage.clients + usage.groups
}

/** Admin bergan tartib birinchi, keyin alifbo */
export function sortRegions(rows: Region[]): Region[] {
  return [...rows].sort(
    (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
  )
}

/* ── O'qish ──────────────────────────────────────────────── */

export function useRegions(includeInactive = false) {
  return useQuery({
    queryKey: ['regions', { includeInactive }],
    queryFn: () => api.get<Region[]>('/regions', { include_inactive: includeInactive }),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Biriktirish uchun hududlar ro'yxati (nomlar).
 *
 * Tanlash uchun faqat FAOL hududlar chiqadi, lekin yozuvda allaqachon
 * turgan hudud faolsizlantirilgan bo'lsa ham ro'yxatda qoladi —
 * aks holda tahrirlash modali ochilganda saqlangan qiymat jimgina
 * yo'qolib ketardi.
 */
export function useRegionChoices(keep?: string | null) {
  const query = useRegions(true)

  const names = useMemo(() => {
    const list = sortRegions(query.data ?? [])
      .filter((region) => region.is_active)
      .map((region) => region.name)
    if (keep && !list.includes(keep)) list.unshift(keep)
    return list
  }, [query.data, keep])

  return { names, isLoading: query.isLoading, isError: query.isError }
}

/* ── Yozish ──────────────────────────────────────────────── */

/**
 * Hudud o'zgarsa nima eskiradi.
 *
 * Nom kaskad bo'lib xodim, mijoz va guruhlarga tarqaladi, ular esa
 * analitika va so'rovnomalarga kiradi — shuning uchun keng tozalanadi.
 */
function useInvalidateRegions() {
  const queryClient = useQueryClient()
  return () => {
    for (const key of [
      'regions',
      'agents',
      'groups',
      'clients',
      'analytics',
      'surveys',
    ]) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }
}

export function useCreateRegion() {
  const invalidate = useInvalidateRegions()
  return useMutation({
    mutationFn: (body: RegionInput & { name: string }) =>
      api.post<Region>('/regions', body),
    onSuccess: invalidate,
  })
}

/**
 * Arxivlash oqibatini OLDINDAN so'raydi.
 *
 * Ogohlantirish taxminga emas, aniq songa asoslansin: «12 ta faol
 * guruh uziladi va so'rovnoma olishni to'xtatadi».
 */
export function useArchivePreview(regionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['region-archive-preview', regionId],
    queryFn: () => api.get<ArchivePreview>(`/regions/${regionId}/archive-preview`),
    enabled: Boolean(regionId) && enabled,
  })
}

export function useUpdateRegion() {
  const invalidate = useInvalidateRegions()
  return useMutation({
    mutationFn: ({ id, ...body }: RegionInput & { id: string }) =>
      api.patch<SavedRegion>(`/regions/${id}`, body),
    onSuccess: invalidate,
  })
}

export function useDeleteRegion() {
  const invalidate = useInvalidateRegions()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/regions/${id}`),
    onSuccess: invalidate,
  })
}

/* ── Xatolar ─────────────────────────────────────────────── */

/** 409 — xato emas, kutilgan javob (band nom yoki ishlatilayotgan hudud) */
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}

/**
 * Backendning o'zbekcha xabari, bo'lmasa — mahalliy matn.
 *
 * `code === 'error'` degani javob konvertida kelmagan va `message`
 * «So'rov muvaffaqiyatsiz (409)» kabi texnik satr. Bunday xom matn
 * foydalanuvchiga ko'rsatilmaydi.
 */
export function conflictMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.code && error.code !== 'error') {
    return error.message
  }
  return fallback
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message ? error.message : fallback
}
