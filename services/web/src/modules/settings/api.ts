/**
 * AI provayderlari reyestri va ulanish sinovi.
 *
 * Ro'yxat kodga yozilmagan — backend `/settings/ai/providers` dan
 * keladi. Model nomlari esa faqat TAKLIF: vendor yangi model chiqarsa
 * admin uni qo'lda yozadi, biz relizini kutmaymiz.
 */

import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/shared/api/client'

export type AiRole = 'asr' | 'llm'

export const AI_ROLES: AiRole[] = ['asr', 'llm']

export interface AiProvider {
  key: string
  label: string
  roles: AiRole[]
  /** Qaysi sozlamada shu provayderning kaliti turadi */
  api_key_setting: string
  key_label: string
  models: Record<AiRole, string[]>
  default_models: Partial<Record<AiRole, string>>
  docs_url: string
  hint: string
}

export interface AiTestResult {
  ok: boolean
  role: AiRole
  role_label: string
  provider: string
  provider_label: string
  model: string
  latency_ms: number
  /** Muvaffaqiyatsiz bo'lsa — backendning o'zbekcha izohi */
  error?: string
  code?: string
}

export const useAiProviders = () =>
  useQuery({
    queryKey: ['settings', 'ai-providers'],
    queryFn: () => api.get<AiProvider[]>('/settings/ai/providers'),
    // Reyestr deploy bilan o'zgaradi — seans davomida qayta so'ralmaydi
    staleTime: Infinity,
  })

/** Vendorda HOZIR mavjud modellar — kodda emas, provayder API'sidan */
export interface AiModelCatalog {
  role: AiRole
  provider: string
  provider_label: string
  models: string[]
  default: string
  /** `live` — vendordan olindi, `fallback` — zaxira ro'yxat */
  source: 'live' | 'fallback'
  note: string | null
}

export const useAiModels = () =>
  useQuery({
    queryKey: ['settings', 'ai-models'],
    queryFn: () => api.get<AiModelCatalog[]>('/settings/ai/models'),
    // Backend 10 daqiqa keshlaydi — bu yerda qayta so'rashning ma'nosi yo'q
    staleTime: 5 * 60_000,
  })

export const useAiTest = () =>
  useMutation({
    mutationFn: (role: AiRole) =>
      api.post<AiTestResult>('/settings/ai/test', { role }),
  })

/** Sozlamadagi kalitlar — rol bo'yicha */
export const providerKeyOf = (role: AiRole) => `ai.${role}_provider`
export const modelKeyOf = (role: AiRole) => `ai.${role}_model`
