/**
 * Baholanmagan qo'ng'iroqlarni ommaviy baholashga qo'yish.
 *
 * NEGA MODAL. Bu amal PUL SARFLAYDI: har qo'ng'iroq bitta ASR va bitta
 * LLM chaqiruvi. 300 ta qo'ng'iroq — 300 tadan. Shuning uchun u bir
 * bosishlik tugma emas: oraliq tanlanadi, oqibat yozilib turadi, va
 * natija «navbatga qo'yildi» degan hisobot bo'lib qaytadi.
 *
 * NEGA «BAJARILDI» DEYILMAYDI. Baholash navbatda, fon rejimida ketadi
 * va daqiqalar oladi. Modal yopilganda ish tugagan bo'lmaydi — shuning
 * uchun matn ham «navbatga qo'yildi» deydi va navbat holatini ko'rsatadi.
 */

import { CheckCircle2, Sparkles, TriangleAlert, User } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  usePipelineStatus,
  useRunPipeline,
  type RunResponse,
} from '@/modules/pipeline/api'
import { useAgents } from '@/modules/agents/api'
import { useScoringBatch } from '@/modules/pipeline/progress'
import { ApiError } from '@/shared/api/client'
import { rangeToQuery, resolvePreset, type DateRange } from '@/shared/lib/date'
import { formatNumber } from '@/shared/lib/utils'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { Modal } from '@/shared/ui/Modal'
import { MultiSelect, type MultiSelectOption } from '@/shared/ui/MultiSelect'
import { Button, Label, Segmented } from '@/shared/ui/primitives'

export function ScoreModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const run = useRunPipeline()
  const startBatch = useScoringBatch((state) => state.start)

  const [range, setRange] = useState<DateRange>(() => resolvePreset('last7'))
  /* Nechta qo'ng'iroq baholansin.

     ⚠️ Standart ATAYLAB kichik. Har qo'ng'iroq pul turadi, va birinchi
     yurishda sozlama to'g'riligini tekshirish kerak — 4000 ta qo'ng'iroqda
     xato takrorlansa, pul ham ketadi, natijaga ishonch ham qolmaydi.
     Kattaroq qiymatni admin ONGLI ravishda tanlaydi. */
  const [limit, setLimit] = useState('20')
  const [agentIds, setAgentIds] = useState<string[]>([])
  const [result, setResult] = useState<RunResponse | null>(null)
  const [problem, setProblem] = useState<string | null>(null)

  const agents = useAgents()
  const agentOptions = useMemo<MultiSelectOption[]>(
    () =>
      (agents.data ?? []).map((agent) => ({
        value: agent.id,
        label: agent.full_name,
        hint: agent.region,
      })),
    [agents.data],
  )

  // Navbat holati faqat ish yuborilgandan keyin kuzatiladi — bu
  // endpoint har chaqiruvda workerlardan so'raydi, bekorga emas
  const watching = Boolean(result?.queued)
  const status = usePipelineStatus(open && watching)

  useEffect(() => {
    if (!open) return
    setRange(resolvePreset('last7'))
    setLimit('20')
    setAgentIds([])
    setResult(null)
    setProblem(null)
  }, [open])

  const start = () => {
    setProblem(null)
    const query = rangeToQuery(range)
    run.mutate(
      {
        date_from: query.date_from,
        date_to: query.date_to,
        // Allaqachon baholanganlar OLINMAYDI — bir xil oraliqni ikki
        // marta yuborish bejiz xarajat qilmaydi
        only_unscored: true,
        limit: Number(limit),
        // Bo'sh ro'yxat — «hamma xodim». Bo'sh massiv yuborilsa
        // backend uni «hech kim» deb tushunardi.
        agent_ids: agentIds.length ? agentIds : undefined,
      },
      {
        onSuccess: (data) => {
          setResult(data)
          /* Jarayon oynadan TASHQARIDA ham ko'rinsin: qo'ng'iroqlar
             sahifasi tepasidagi chiziq shu holatdan oziqlanadi.
             Oyna yopilsa ham ish davom etadi. */
          startBatch(data.queued)
        },
        onError: (error) =>
          setProblem(
            error instanceof ApiError ? error.message : t('common.error'),
          ),
      },
    )
  }

  const stages = status.data?.stages
  const remaining =
    (stages?.queued ?? 0) + (stages?.transcribing ?? 0) + (stages?.scoring ?? 0)

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={result ? t('pipeline.queuedTitle') : t('pipeline.title')}
      description={result ? undefined : t('pipeline.subtitle')}
      footer={
        result ? (
          <Button variant="secondary" onClick={onClose}>
            {t('common.close')}
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={run.isPending}>
              {t('common.cancel')}
            </Button>
            <Button onClick={start} disabled={run.isPending}>
              <Sparkles className="size-4" />
              {run.isPending ? t('pipeline.starting') : t('pipeline.start')}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className="space-y-3">
          <div className="flex items-start gap-3 rounded-xl bg-good/10 p-3.5 ring-1 ring-good/25">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-good" />
            <div className="min-w-0">
              <div className="tnum text-lg font-semibold">
                {formatNumber(result.queued)}
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                {result.message}
              </p>
            </div>
          </div>

          {/* Navbat kamayib borishi ko'rinib tursin — aks holda
              foydalanuvchi «ishlayaptimi?» deb sahifani yangilaydi */}
          {watching && (
            <div className="rounded-xl bg-surface-2/60 p-3.5">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted">
                  {t('pipeline.remaining')}
                </span>
                <span className="tnum text-sm font-semibold">
                  {formatNumber(remaining)}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-2xs text-muted">
                  {t('pipeline.throughput')}
                </span>
                <span className="tnum text-2xs">
                  {status.data?.per_minute_15min ?? 0} / {t('common.min')}
                </span>
              </div>
              {status.data?.worker_count === 0 && (
                <p className="mt-2 text-2xs leading-relaxed text-bad">
                  {t('pipeline.noWorker')}
                </p>
              )}
            </div>
          )}

          <p className="text-2xs leading-relaxed text-muted">
            {t('pipeline.background')}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t('filters.period')}</Label>
            <DateRangePicker value={range} onChange={setRange} />
          </div>

          <div className="space-y-1.5">
            <Label>{t('pipeline.limit')}</Label>
            <Segmented
              value={limit}
              onChange={setLimit}
              items={[
                { value: '20', label: '20' },
                { value: '100', label: '100' },
                { value: '500', label: '500' },
                { value: '5000', label: t('filters.all') },
              ]}
            />
            <p className="text-2xs leading-relaxed text-muted">
              {t('pipeline.limitHint')}
            </p>
          </div>

          {agentOptions.length > 1 && (
            <div className="space-y-1.5">
              <Label>{t('filters.agents')}</Label>
              <MultiSelect
                icon={User}
                label={t('filters.agents')}
                options={agentOptions}
                value={agentIds}
                onChange={setAgentIds}
                summary={(count) => t('filters.agentCount', { count })}
              />
              <p className="text-2xs leading-relaxed text-muted">
                {t('pipeline.agentHint')}
              </p>
            </div>
          )}

          {/* Oqibat OLDIN aytiladi, keyin emas */}
          <div className="flex items-start gap-2.5 rounded-xl bg-warn/10 p-3.5 ring-1 ring-warn/25">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" />
            <p className="text-2xs leading-relaxed">{t('pipeline.costWarning')}</p>
          </div>

          <p className="text-2xs leading-relaxed text-muted">
            {t('pipeline.skipHint')}
          </p>

          {problem && (
            <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs leading-relaxed text-bad">
              {problem}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}
