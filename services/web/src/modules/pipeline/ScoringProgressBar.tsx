/**
 * Ommaviy baholash jarayoni — qo'ng'iroqlar sahifasi tepasidagi chiziq.
 *
 * Baholash ORQA FONDA ketadi va daqiqalar oladi. Modal oyna yopilgach
 * admin qancha qolganini bilmay qolardi. Endi jarayon sahifaning
 * tepasida chapdan o'ngga to'lib boradi.
 *
 * ⚠️ CHIZIQ ORQAGA QAYTMAYDI. Navbat holati global: shu paytda boshqa
 * ish qo'shilsa «qolgan» soni ko'payadi va foiz kamayardi — ekranda
 * progress sirg'alib orqaga ketgandek ko'rinardi. `progress.ts` dagi
 * `observe()` eng katta erishilgan qiymatni ushlab turadi.
 *
 * Tugagach chiziq darhol yo'qolmaydi: bir necha soniya to'liq yashil
 * bo'lib turadi, aks holda «tugadimi yoki uzilib qoldimi?» degan savol
 * qolardi.
 */

import { CheckCircle2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'

import { usePipelineStatus } from '@/modules/pipeline/api'
import {
  batchFinished,
  batchPercent,
  useScoringBatch,
  type QueueSnapshot,
} from '@/modules/pipeline/progress'
import { cn, formatNumber } from '@/shared/lib/utils'

/** Tugagach chiziq shuncha vaqt to'liq yashil turadi */
const DONE_HOLD_MS = 6000

export function ScoringProgressBar() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const batch = useScoringBatch((state) => state.batch)
  const observe = useScoringBatch((state) => state.observe)
  const stop = useScoringBatch((state) => state.stop)

  const status = usePipelineStatus(Boolean(batch))
  const [finished, setFinished] = useState(false)

  /* ⚠️ Progress «qolgan» dan emas, BAJARILGAN dan hisoblanadi.
     Bosqich sanoqlari (`queued`/`transcribing`/`scoring`) faqat worker
     ishni boshlagandan keyin to'ladi — Redis navbatida kutayotgan
     vazifalar u yerda ko'rinmaydi. Sinovda 3 ta qo'ng'iroq yuborilganda
     «qolgan» boshidan oxirigacha 0 bo'lib turdi, ya'ni unga qarab
     chizilgan chiziq darhol 100% ko'rsatib yolg'on gapirardi.

     `finishedTotal` — terminal holatga yetganlar: tugagan, yiqilgan
     va o'tkazib yuborilganlar. Uchalasi ham «endi kutilmaydi» degani. */
  const data = status.data
  const stages = data?.stages
  const finishedTotal =
    (stages?.completed ?? 0) + (stages?.failed ?? 0) + (stages?.skipped ?? 0)
  const inFlight =
    (data?.queue_depth ?? 0) +
    (data?.active_tasks ?? 0) +
    (stages?.queued ?? 0) +
    (stages?.transcribing ?? 0) +
    (stages?.scoring ?? 0)
  const snapshot: QueueSnapshot | null = data ? { finishedTotal, inFlight } : null

  useEffect(() => {
    if (!batch || !data) return
    observe({ finishedTotal, inFlight })
  }, [batch, data, finishedTotal, inFlight, observe])

  const done = batchFinished(batch, snapshot)

  useEffect(() => {
    if (!done) return
    setFinished(true)
    // Ro'yxat va analitikada yangi ballar ko'rinsin
    for (const key of ['calls', 'analytics']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
    const timer = window.setTimeout(() => {
      setFinished(false)
      stop()
    }, DONE_HOLD_MS)
    return () => window.clearTimeout(timer)
  }, [done, queryClient, stop])

  if (!batch) return null

  const percent = finished ? 100 : batchPercent(batch)
  const processed = finished ? batch.total : batch.done

  return (
    <div className="animate-fade-up card overflow-hidden p-0">
      {/* Chiziq — chapdan o'ngga to'ladi */}
      <div className="h-1.5 w-full bg-surface-2">
        <div
          className="h-full rounded-r-full bg-good transition-[width] duration-500 ease-ios"
          style={{ width: `${Math.max(percent, 2)}%` }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
        <span
          className={cn(
            'grid size-6 shrink-0 place-items-center rounded-full',
            finished ? 'bg-good/15 text-good' : 'bg-surface-2 text-muted',
          )}
        >
          {finished ? (
            <CheckCircle2 className="size-3.5" />
          ) : (
            <Sparkles className="size-3.5 animate-pulse" />
          )}
        </span>

        <span className={cn('text-xs font-medium', finished && 'text-good')}>
          {finished ? t('pipeline.progress.done') : t('pipeline.progress.running')}
        </span>

        <span className="tnum text-2xs text-muted">
          {formatNumber(processed)} / {formatNumber(batch.total)}
        </span>

        <span className="tnum ml-auto text-2xs font-medium text-muted">{percent}%</span>
      </div>
    </div>
  )
}
