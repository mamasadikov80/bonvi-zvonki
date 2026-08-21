import { useQuery } from '@tanstack/react-query'

import { api } from '@/shared/api/client'

/* ── Turlar ──────────────────────────────────────────────── */

export interface AnalyticsQuery {
  days?: number
  date_from?: string
  date_to?: string
  agent_ids?: string[]
  regions?: string[]
  score_min?: number
  score_max?: number
  has_red_flags?: boolean
}

interface Metric {
  value: number | null
  delta_percent: number | null
}

/** Client reytingi — yetarli javob yig'ilmaguncha `ready: false` */
interface RatingMetric extends Metric {
  count: number
  ready: boolean
  /** Amaldagi chegara (`survey.min_responses`) — UI «1 / 5» deb yozadi */
  min_responses: number
}

/** Qo'ng'iroq turlari bo'yicha soni. Kalitlar BACKENDdan keladi va
 *  nol bo'lsa ham to'la bo'ladi — UI ro'yxatni o'zi to'ldirmasligi
 *  kerak, aks holda ikki tomon ajralib ketadi. */
export interface CallTypeCounts {
  sales: number
  /** Ikki xodim o'rtasidagi suhbat — baholanmaydi */
  internal: number
  /** Hali aniqlanmagan */
  unknown: number
}

export interface Overview {
  /** ⚠️ BAHOLANGAN qo'ng'iroqlar soni — savdo suhbatlari.
   *  Savdo bo'lmagan suhbatda baho qatori yozilmaydi, ya'ni ular bu
   *  songa kirmaydi. Jamisi — `calls_total`. */
  calls: Metric
  call_types: CallTypeCounts
  /** Davrdagi BARCHA tugallangan qo'ng'iroq */
  calls_total: number
  ai_score: Metric
  client_rating: RatingMetric
  red_flags: Metric
  avg_duration_sec: number
}

export interface TrendPoint {
  date: string
  calls: number
  ai_score: number | null
  client_rating: number | null
}

export interface AgentRow {
  agent_id: string
  full_name: string
  region: string
  color: string
  avatar_url: string | null
  calls: number
  ai_score: number | null
  client_rating: number | null
  client_rating_count: number
  client_rating_ready: boolean
  divergence: number | null
  divergence_flag: boolean
  red_flags: number
  avg_duration_sec: number
  rank: number
  /** Oldingi davrga nisbatan o'rin o'zgarishi (musbat = ko'tarildi) */
  rank_delta: number | null
}

export interface BlockRow {
  block: string
  label: string
  score: number
  max: number
  percent: number
}

export interface RedFlagRow {
  type: string
  label: string
  count: number
}

export interface DistributionRow {
  range: string
  count: number
}

export interface RegionRow {
  region: string
  calls: number
  ai_score: number | null
}

export interface FilterOptions {
  agents: { id: string; name: string; region: string }[]
  regions: string[]
}

/* ── Hooklar ─────────────────────────────────────────────── */

const key = (name: string, q: AnalyticsQuery) => ['analytics', name, q] as const

export const useOverview = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('overview', q),
    queryFn: () => api.get<Overview>('/analytics/overview', q as never),
  })

export const useTrend = (q: AnalyticsQuery, bucket: 'day' | 'week' = 'day') =>
  useQuery({
    queryKey: [...key('trend', q), bucket],
    queryFn: () => api.get<TrendPoint[]>('/analytics/timeseries', { ...q, bucket } as never),
  })

export const useAgentLeaderboard = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('agents', q),
    queryFn: () => api.get<AgentRow[]>('/analytics/agents', q as never),
  })

export const useBlocks = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('blocks', q),
    queryFn: () => api.get<BlockRow[]>('/analytics/blocks', q as never),
  })

export const useRedFlags = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('red-flags', q),
    queryFn: () => api.get<RedFlagRow[]>('/analytics/red-flags', q as never),
  })

export const useDistribution = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('distribution', q),
    queryFn: () => api.get<DistributionRow[]>('/analytics/distribution', q as never),
  })

export const useRegions = (q: AnalyticsQuery) =>
  useQuery({
    queryKey: key('regions', q),
    queryFn: () => api.get<RegionRow[]>('/analytics/regions', q as never),
  })

export const useFilterOptions = () =>
  useQuery({
    queryKey: ['analytics', 'filters'],
    queryFn: () => api.get<FilterOptions>('/analytics/filters'),
    staleTime: 5 * 60 * 1000,
  })
