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
  first_call_at: string
  last_call_at: string
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

/** Bitta mijoz — BUTUN tarixi bo'yicha (davr filtri qo'yilmaydi) */
export const useClient = (key: string | undefined) =>
  useQuery({
    queryKey: ['clients', 'detail', key],
    queryFn: () => api.get<ClientDetail>(`/clients/${key}`),
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
  query: { page?: number; page_size?: number } = {},
) =>
  useQuery({
    queryKey: ['clients', 'calls', key, query],
    queryFn: () =>
      api.get<PaginatedClientCalls>(`/clients/${key}/calls`, query as never),
    enabled: Boolean(key),
  })
