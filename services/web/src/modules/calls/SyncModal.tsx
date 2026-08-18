/**
 * MoyZvonki'dan qo'ng'iroqlarni tortib olish.
 *
 * QOIDA: har qanday amal modalda. Bu yerda buning yana bir sababi bor —
 * sinxronizatsiya sana oralig'ini so'raydi va natijasi hisobot bo'ladi
 * (nechtasi yangi, nechtasi yangilandi, nechtasi tashlab ketildi).
 * Sahifaga inline joylashtirilsa hisobot yo'qolib ketardi.
 *
 * Faqat metadata ko'chiriladi. Audio bizda saqlanmaydi — yozuv faqat
 * tinglash paytida MoyZvonki'dan oqim bilan o'tadi.
 */

import { CheckCircle2, CloudDownload, PlugZap, TriangleAlert, User } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgents } from '@/modules/agents/api'
import { useSyncCalls, useSyncWindow, type SyncResult } from '@/modules/calls/api'
import { ApiError } from '@/shared/api/client'
import {
  localDate,
  customRange,
  rangeToQuery,
  type DateRange,
} from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { MultiSelect, type MultiSelectOption } from '@/shared/ui/MultiSelect'
import {
  Badge,
  Button,
  Label,
  Segmented,
  Skeleton,
} from '@/shared/ui/primitives'

interface Problem {
  code: string
  message: string
}

/** Sinxronizatsiya davrlari (kun).
 *
 *  ⚠️ 45 dan kattasi YO'Q va bo'lmaydi: MoyZvonki yozuvni cheklangan
 *  muddat saqlaydi, undan narisida audio deyarli qolmaydi. Kengroq
 *  oraliq tanlash imkoniyati faqat uzoq kutish va bo'sh natijaga olib
 *  kelardi — backend ham so'rovni 45 kunga qisqartiradi. */
const SYNC_PERIODS = [7, 30, 45] as const
type SyncDays = (typeof SYNC_PERIODS)[number]

/** «Oxirgi N kun» — bugun ham to'liq kiradi. */
function lastDays(days: SyncDays): DateRange {
  const to = new Date()
  const from = new Date(to)
  from.setDate(from.getDate() - (days - 1))
  from.setHours(0, 0, 0, 0)
  return customRange(from, to)
}

export function SyncModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const sync = useSyncCalls()
  /* Qancha orqaga tanlash mumkin — chegarani BACKEND aytadi.
     Undan oldingi kunni tanlashning ma'nosi yo'q: qo'ng'iroq
     metadatasi kelaveradi, lekin audiosi bo'lmagani uchun bitta ham
     qator bazaga tushmaydi. */
  const window = useSyncWindow(open)
  /* `new Date('2026-07-03')` UTC yarim tunini beradi, tayyor davrlar
     esa MAHALLIY yarim tunda boshlanadi. Toshkentda (UTC+5) bu 5 soatlik
     siljish demak: aynan chegara kunidan boshlanadigan davr «chegaradan
     oldin» deb hisoblanib, ro'yxatdan tushib qolardi. */
  const earliest = window.data ? localDate(window.data.earliest) : null

  /* Faqat uch variant. Murakkab sana tanlagich bu yerda keraksiz:
     MoyZvonki yozuvni cheklangan muddat saqlaydi va 45 kundan
     narisida audio deyarli qolmaydi — ya'ni kengroq oraliq tanlash
     imkoniyati faqat bo'sh urinishga olib kelardi. */
  const [days, setDays] = useState<SyncDays>(7)
  /* Qaysi xodimlarning qo'ng'iroqlari saqlanadi. Bo'sh — hammasi.

     ⚠️ Ilgari bu yerda `supervised` tugmachasi turardi. U MoyZvonki'ning
     ICHKI tushunchasini ochib qo'yardi («API kalit egasining qo'ng'iroqlari»)
     va admin uni bosib nima o'zgarishini bilolmasdi — amalda uni o'chirish
     deyarli har doim XATO edi, chunki o'shanda faqat bitta hisobning
     qo'ng'iroqlari kelardi. Endi tanlov tushunarli narsada: BIZNING
     xodimlarimiz.

     `supervised` o'zi qoladi va doim `true` — MoyZvonki'dan hamma
     xodimning qo'ng'irog'i o'qiladi, filtrlash esa bizda bo'ladi
     (`calls.list` da xodim bo'yicha parametr yo'q). */
  const [agentIds, setAgentIds] = useState<string[]>([])
  const [result, setResult] = useState<SyncResult | null>(null)
  const [problem, setProblem] = useState<Problem | null>(null)

  const agents = useAgents()
  const agentOptions = useMemo<MultiSelectOption[]>(
    () =>
      (agents.data ?? [])
        // MoyZvonki bilan bog'lanmagan xodimning qo'ng'irog'i
        // baribir kelmaydi — ro'yxatda ko'rsatish chalg'itardi
        .filter((agent) => agent.external_id)
        .map((agent) => ({
          value: agent.id,
          label: agent.full_name,
          hint: agent.region,
        })),
    [agents.data],
  )

  // Har ochilishda toza holat — o'tgan safargi hisobot yangi
  // oraliqqa tegishlidek ko'rinib qolmasin
  useEffect(() => {
    if (!open) return
    setDays(7)
    setAgentIds([])
    setResult(null)
    setProblem(null)
  }, [open])

  const run = () => {
    setProblem(null)
    const query = rangeToQuery(lastDays(days))
    sync.mutate(
      {
        date_from: query.date_from,
        date_to: query.date_to,
        supervised: true,
        agent_ids: agentIds.length ? agentIds : undefined,
      },
      {
        onSuccess: (data) => setResult(data),
        onError: (error) =>
          setProblem(
            error instanceof ApiError
              ? { code: error.code, message: error.message }
              : { code: 'error', message: t('common.error') },
          ),
      },
    )
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={result ? t('calls.sync.doneTitle') : t('calls.sync.title')}
      description={result ? undefined : t('calls.sync.hint')}
      size="md"
      footer={
        result ? (
          <Button onClick={onClose}>{t('common.close')}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={sync.isPending}>
              {t('common.cancel')}
            </Button>
            <Button disabled={sync.isPending} onClick={run}>
              {sync.isPending ? t('calls.sync.running') : t('calls.sync.start')}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <SyncReport result={result} />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <Label className="mb-0.5">{t('calls.sync.period')}</Label>
              <p className="text-2xs text-muted">{t('calls.sync.periodHint')}</p>
            </div>
            <Segmented
              value={String(days)}
              onChange={(value) => setDays(Number(value) as SyncDays)}
              items={SYNC_PERIODS.map((d) => ({
                value: String(d),
                label: t(`calls.sync.period.d${d}`),
              }))}
            />
          </div>

          {agentOptions.length > 1 && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <Label className="mb-0.5">{t('filters.agents')}</Label>
                <p className="text-2xs text-muted">{t('calls.sync.agentHint')}</p>
              </div>
              <MultiSelect
                icon={User}
                label={t('filters.agents')}
                options={agentOptions}
                value={agentIds}
                onChange={setAgentIds}
                summary={(count) => t('filters.agentCount', { count })}
              />
            </div>
          )}

          {earliest && window.data && (
            <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
              {t('calls.sync.windowNote', {
                date: earliest.toLocaleDateString('ru-RU'),
                days: window.data.days,
              })}
            </p>
          )}

          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('calls.sync.noAudioNote')}
          </p>

          {/* Uzoq davom etishi mumkin — spinner emas, skelet */}
          {sync.isPending && (
            <div className="space-y-2">
              <p className="text-2xs text-muted">{t('calls.sync.runningHint')}</p>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          )}

          {problem && <ProblemNote problem={problem} />}
        </div>
      )}
    </Modal>
  )
}

/* ── Nosozlik ─────────────────────────────────────────────────
   «Sozlanmagan» — buzilish emas, shunchaki hali ulanmagan. Shuning
   uchun u qizil emas, xotirjam izoh bilan chiqadi. */

function ProblemNote({ problem }: { problem: Problem }) {
  const { t } = useTranslation()
  const calm = problem.code === 'moizvonki_not_configured'

  return (
    <div
      className={cn(
        'flex animate-scale-in items-start gap-3 rounded-2xl p-3.5',
        calm ? 'bg-surface-2/70' : 'bg-bad/[0.08]',
      )}
    >
      <span
        className={cn(
          'icon-tile size-9 shrink-0',
          calm ? 'bg-surface-2 text-muted' : 'text-bad',
        )}
      >
        {calm ? <PlugZap className="size-4" /> : <TriangleAlert className="size-4" />}
      </span>
      <div className="min-w-0">
        <p className={cn('text-xs font-medium', !calm && 'text-bad')}>
          {calm ? t('calls.sync.notConfigured') : t('calls.sync.failed')}
        </p>
        <p className="mt-0.5 text-2xs leading-relaxed text-muted">{problem.message}</p>
      </div>
    </div>
  )
}

/* ── Hisobot ─────────────────────────────────────────────────── */

function SyncReport({ result }: { result: SyncResult }) {
  const { t } = useTranslation()
  const clean = result.skipped_no_agent === 0

  const rows: { key: string; value: number; tone?: 'good' | 'muted' }[] = [
    { key: 'created', value: result.created, tone: 'good' },
    { key: 'updated', value: result.updated },
    { key: 'fetched', value: result.fetched },
    { key: 'skippedAgent', value: result.skipped_no_agent, tone: 'muted' },
    { key: 'skippedRecording', value: result.skipped_no_recording, tone: 'muted' },
  ]

  return (
    <div className="space-y-4">
      <div
        className={cn(
          'flex items-start gap-3 rounded-2xl p-4',
          clean ? 'bg-good/10' : 'bg-warn/[0.08]',
        )}
      >
        <span
          className={cn('icon-tile size-10 shrink-0', clean ? 'text-good' : 'text-warn')}
        >
          {clean ? (
            <CheckCircle2 className="size-5" />
          ) : (
            <TriangleAlert className="size-5" />
          )}
        </span>
        <div className="min-w-0">
          <p className={cn('text-sm font-semibold', clean ? 'text-good' : 'text-warn')}>
            {t('calls.sync.created', { count: result.created })}
          </p>
          {/* Backendning o'zbekcha xulosasi — o'zgartirilmaydi */}
          <p className="mt-1 text-xs leading-relaxed text-muted">{result.message}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {rows.map((row) => (
          <div key={row.key} className="rounded-xl bg-surface-2/60 px-3.5 py-3">
            <div className="text-2xs text-muted">{t(`calls.sync.${row.key}`)}</div>
            <div
              className={cn(
                'tnum mt-0.5 text-lg font-semibold',
                row.tone === 'good' && row.value > 0 && 'text-good',
                row.tone === 'muted' && row.value > 0 && 'text-warn',
              )}
            >
              {formatNumber(row.value)}
            </div>
          </div>
        ))}
      </div>

      {result.truncated && (
        <p className="rounded-xl bg-warn/[0.09] px-3.5 py-3 text-2xs leading-relaxed text-warn">
          {t('calls.sync.truncated')}
        </p>
      )}

      {/* Xodimga bog'lanmagan egalar — aynan shu ro'yxat keyingi qadamni
          aytadi: «Xodimlar» bo'limida MoyZvonki identifikatorini to'ldirish */}
      {result.unmatched.length > 0 && (
        <div className="rounded-2xl bg-surface-2/60 p-3.5">
          <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-muted">
            <CloudDownload className="size-3.5" />
            {t('calls.sync.unmatched')}
          </div>
          <ul className="max-h-44 space-y-1.5 overflow-y-auto">
            {result.unmatched.map((owner, index) => (
              <li key={index} className="flex items-center gap-2 text-xs">
                <span className="truncate font-medium">{owner.label}</span>
                <Badge className="ml-auto shrink-0">
                  <span className="tnum">{formatNumber(owner.call_count)}</span>
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
