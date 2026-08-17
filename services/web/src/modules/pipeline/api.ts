/**
 * AI quvuri — API qatlami.
 *
 * Quvur qo'ng'iroqni ikki bosqichda o'tkazadi: yozuvni matnga (ASR),
 * so'ng matnni rubrika bo'yicha baholash (LLM). Ikkalasi ham pul turadi
 * va o'nlab soniya oladi, shuning uchun ish HTTP so'rovi ichida emas,
 * NAVBATDA bajariladi: endpoint faqat «navbatga qo'ydim» deb javob
 * qaytaradi, natija esa bir necha daqiqadan keyin paydo bo'ladi.
 *
 * Shu sababli UI ham «bajarildi» deb yozmaydi — «navbatga qo'yildi»
 * deydi va holatni kuzatish yo'lini ko'rsatadi.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'

/* ── Turlar ──────────────────────────────────────────────── */

export interface RunResponse {
  /** Navbatga qo'yilgan qo'ng'iroqlar soni. `0` — baholanadigani yo'q */
  queued: number
  date_from: string
  date_to: string
  force: boolean
  task_ids: string[]
  /** Backend tayyorlagan o'zbekcha xabar — UI uni takrorlamaydi */
  message: string
}

export interface RunRequest {
  date_from: string
  date_to: string
  /** `true` — allaqachon baholanganlar OLINMAYDI (takroriy xarajat yo'q) */
  only_unscored?: boolean
  /** `true` — mavjud baho ustiga yoziladi. Qimmat, ehtiyot bo'ling */
  force?: boolean
  limit?: number
  /** Bo'sh yoki berilmagan — barcha xodimlar */
  agent_ids?: string[]
}

export interface PipelineStatus {
  /** `queued | transcribing | scoring | completed | failed | skipped` */
  stages: Record<string, number>
  workers: string[]
  worker_count: number
  /** Hozir bajarilayotgan vazifalar. `null` — worker so'roviga javob yo'q */
  active_tasks: number | null
  reserved_tasks: number | null
  /** Redis navbatida kutayotganlar. `null` — Redis javob bermadi */
  queue_depth: number | null
  scored_last_hour: number
  scored_last_15min: number
  per_minute_15min: number
  needs_review_pending: number
  checked_at: string
}

/* ── Hooklar ─────────────────────────────────────────────── */

/**
 * Baho o'zgargach nima eskiradi.
 *
 * Baholash natijasi qo'ng'iroq kartochkasida ham, jadvalda ham,
 * butun analitikada ham ko'rinadi — shuning uchun keng tozalanadi.
 * Navbatga qo'yish paytida natija hali yo'q, lekin «tekshirilmoqda»
 * holatini ko'rsatish uchun ro'yxat yangilanadi.
 */
function useInvalidatePipeline() {
  const queryClient = useQueryClient()
  return () => {
    for (const key of ['calls', 'call', 'analytics', 'pipeline']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }
}

/** Bitta qo'ng'iroqni qayta baholashga yuborish. */
export function useRetryCall() {
  const invalidate = useInvalidatePipeline()
  return useMutation({
    mutationFn: ({ callId, force = true }: { callId: string; force?: boolean }) =>
      api.post<RunResponse>(
        `/pipeline/calls/${callId}/retry?force=${force}`,
        {},
      ),
    onSuccess: invalidate,
  })
}

/** Sana oralig'idagi qo'ng'iroqlarni ommaviy baholashga qo'yish. */
export function useRunPipeline() {
  const invalidate = useInvalidatePipeline()
  return useMutation({
    mutationFn: (body: RunRequest) => api.post<RunResponse>('/pipeline/run', body),
    onSuccess: invalidate,
  })
}

/**
 * Navbat holati.
 *
 * `enabled` — faqat kerak bo'lganda so'raladi: bu endpoint har
 * chaqiruvda Celery workerlaridan so'rov qiladi (broadcast), shuning
 * uchun uni doimiy pollingda ushlab turish keraksiz yuk.
 */
export function usePipelineStatus(enabled = false) {
  return useQuery({
    queryKey: ['pipeline', 'status'],
    queryFn: () => api.get<PipelineStatus>('/pipeline/status'),
    enabled,
    refetchInterval: enabled ? 5_000 : false,
  })
}
