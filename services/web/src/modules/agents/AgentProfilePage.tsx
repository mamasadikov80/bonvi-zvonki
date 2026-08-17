import { AlertTriangle, ChevronRight, Clock, Phone, Star, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

import {
  useAgentLeaderboard,
  useBlocks,
  useOverview,
  useTrend,
} from '@/modules/analytics/api'
import { useAgent, useFeedback, type FeedbackSummary } from '@/modules/agents/api'
import { useAuth } from '@/modules/auth/store'
import { useCalls } from '@/modules/calls/api'
import { ratingProgress } from '@/modules/surveys/api'
import { BlocksChart, TrendChart } from '@/modules/dashboard/components/charts'
import { KpiCard } from '@/modules/dashboard/components/KpiCard'
import { Page, PageHeader } from '@/shared/layout/Page'
import {
  rangeToQuery,
  resolvePreset,
  useDateFormat,
  type DateRange,
} from '@/shared/lib/date'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { cn, formatDuration, formatNumber, scoreTone, TONE_CLASS } from '@/shared/lib/utils'
import { Avatar, MiniBar, ScoreRing } from '@/shared/ui/dataviz'
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Skeleton,
} from '@/shared/ui/primitives'

export function AgentProfilePage() {
  const { t } = useTranslation()
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const { can, user } = useAuth()

  const fmt = useDateFormat()
  const [range, setRange] = useState<DateRange>(() => resolvePreset('last30'))
  const query = {
    ...rangeToQuery(range),
    agent_ids: agentId ? [agentId] : undefined,
  }

  const agent = useAgent(agentId)
  const overview = useOverview(query)
  const trend = useTrend(query)
  const blocks = useBlocks(query)
  // ⚠️ Reyting ham TANLANGAN ORALIQDAN. Ilgari bu yerda `{ days }`
  // turardi va sarlavhadagi ball halqasi bilan o'rin raqami sahifaning
  // qolgan qismidan boshqa davrni ko'rsatardi: «o'tgan oy» tanlanганda
  // KPI «0 qo'ng'iroq» der, halqa esa 88.8 ball ko'rsatardi.
  const leaderboard = useAgentLeaderboard(rangeToQuery(range))
  const calls = useCalls({ page: 1, page_size: 8, agent_id: agentId })

  const canSeeFeedback = can('surveys:read') || can('surveys:read:own')
  const feedback = useFeedback({
    agent_id: agentId,
    ...rangeToQuery(range),
    limit: 12,
    enabled: canSeeFeedback,
  })

  const row = leaderboard.data?.find((r) => r.agent_id === agentId)
  const tone = scoreTone(row?.ai_score) as 'accent' | 'good' | 'warn' | 'bad'
  const series = trend.data ?? []

  if (agent.isLoading) {
    return (
      <Page>
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </Page>
    )
  }

  if (!agent.data) {
    return (
      <Page>
        <EmptyState message={t('table.empty')} />
      </Page>
    )
  }

  const a = agent.data

  return (
    <Page>
      <PageHeader
        title={a.full_name}
        subtitle={[
          a.regions?.length ? a.regions.join(', ') : t('agents.noRegion'),
          a.hired_at ? `${t('agents.since')} ${fmt.date(a.hired_at)}` : null,
        ]
          .filter(Boolean)
          .join(' · ')}
        actions={<DateRangePicker value={range} onChange={setRange} />}
      />

      {/* ── Profil sarlavhasi ─────────────────────────────── */}
      <Card>
        <CardBody className="flex flex-wrap items-center gap-5">
          <Avatar name={a.full_name} color={a.color} src={a.avatar_url} size="lg" />

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-semibold">{a.full_name}</span>
              {/* Xizmat hududlari — Telegram guruhlari bo'limidagi bilan
                  AYNAN bir xil manbadan. Bir nechta bo'lsa hammasi. */}
              {a.regions?.length ? (
                a.regions.map((name) => <Badge key={name}>{name}</Badge>)
              ) : (
                <Badge tone="warn">{t('agents.noRegion')}</Badge>
              )}
              {!a.is_active && <Badge tone="bad">{t('agents.inactive')}</Badge>}
              {row && (
                <Badge tone="accent">
                  {t('agents.rank')} #{row.rank}
                </Badge>
              )}
            </div>
            {a.phone && (
              <div className="tnum mt-1 text-xs text-muted">{a.phone}</div>
            )}
          </div>

          <ScoreRing value={row?.ai_score ?? null} tone={tone} size={72} />
        </CardBody>
      </Card>

      {/* ── KPI ───────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 2xl:gap-4">
        <KpiCard
          icon={Phone}
          label={t('kpi.calls')}
          value={overview.data ? formatNumber(overview.data.calls.value ?? 0) : null}
          delta={overview.data?.calls.delta_percent}
          spark={series.map((p) => p.calls)}
          loading={overview.isLoading}
        />
        <KpiCard
          icon={TrendingUp}
          label={t('kpi.aiScore')}
          value={overview.data?.ai_score.value ?? null}
          suffix="/ 100"
          delta={overview.data?.ai_score.delta_percent}
          spark={series.map((p) => p.ai_score)}
          tone="good"
          loading={overview.isLoading}
        />
        {/* Client bahosi — chegaraga yetmaganda «—» EMAS.
            Bo'sh chiziq «ishlamayapti» degan xulosaga olib keladi
            (real hodisa: 4★ baho keldi, admin buzuq deb o'yladi). */}
        <ClientRatingKpi
          summary={feedback.data}
          loading={feedback.isLoading}
          visible={canSeeFeedback}
        />
        <KpiCard
          icon={AlertTriangle}
          label={t('kpi.redFlags')}
          value={overview.data?.red_flags.value ?? null}
          delta={overview.data?.red_flags.delta_percent}
          invertDelta
          tone="bad"
          loading={overview.isLoading}
        />
      </div>

      {/* ── Trend + rubrika ───────────────────────────────── */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] 2xl:gap-4">
        <Card>
          <CardHeader title={t('chart.trend')} hint={t('chart.trendHint')} />
          <CardBody className="pt-2">
            {trend.isLoading ? (
              <Skeleton className="h-[260px] w-full" />
            ) : (
              <TrendChart data={series} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={t('chart.blocks')} />
          <CardBody className="pt-2">
            {blocks.isLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : (
              <BlocksChart data={blocks.data ?? []} />
            )}
          </CardBody>
        </Card>
      </div>

      {/* ── Qo'ng'iroqlar + client fikrlari ───────────────── */}
      <div className="grid gap-3 xl:grid-cols-2 2xl:gap-4">
        {/* Oxirgi qo'ng'iroqlar */}
        <Card>
          <CardHeader
            title={t('agents.recentCalls')}
            action={
              <button
                onClick={() => navigate(`/calls?agent_id=${agentId}`)}
                className="text-2xs font-medium text-accent hover:underline"
              >
                {t('agents.viewAll')}
              </button>
            }
          />
          <CardBody className="space-y-1.5 pt-3">
            {calls.isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))
            ) : !calls.data?.items.length ? (
              <EmptyState message={t('table.empty')} />
            ) : (
              calls.data.items.map((call) => {
                const callTone = scoreTone(call.score) as
                  | 'accent'
                  | 'good'
                  | 'warn'
                  | 'bad'
                return (
                  <button
                    key={call.id}
                    onClick={() => navigate(`/calls/${call.id}`)}
                    className="flex w-full items-center gap-3 rounded-xl bg-surface-2/60 p-3 text-left transition-all duration-250 ease-ios hover:bg-surface-2 active:scale-[0.99]"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {call.client_name ?? '—'}
                      </div>
                      <div className="tnum text-2xs text-muted">
                        {fmt.dateTime(call.started_at)} ·{' '}
                        {formatDuration(call.duration_sec)}
                      </div>
                    </div>

                    {call.red_flag_count > 0 && (
                      <Badge tone="bad">
                        <AlertTriangle className="size-3" />
                        <span className="tnum">{call.red_flag_count}</span>
                      </Badge>
                    )}

                    <span
                      className={cn(
                        'tnum shrink-0 text-sm font-semibold',
                        TONE_CLASS[callTone],
                      )}
                    >
                      {call.score ?? '—'}
                    </span>
                    <ChevronRight className="size-4 shrink-0 text-muted" />
                  </button>
                )
              })
            )}
          </CardBody>
        </Card>

        {/* Client fikrlari */}
        <Card>
          <CardHeader
            title={t('agents.clientFeedback')}
            hint={
              feedback.data?.response_rate != null
                ? t('agents.responseRate', { rate: feedback.data.response_rate })
                : undefined
            }
          />
          <CardBody className="pt-3">
            {!canSeeFeedback ? (
              <EmptyState message={t('agents.feedbackHidden')} />
            ) : feedback.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : !feedback.data?.count ? (
              <EmptyState message={t('common.noData')} />
            ) : (
              <>
                {/* Yulduzlar taqsimoti */}
                <div className="mb-4 space-y-1.5">
                  {[5, 4, 3, 2, 1].map((star) => {
                    const count = feedback.data.distribution[String(star)] ?? 0
                    const pct = (count / feedback.data.count) * 100
                    return (
                      <div key={star} className="flex items-center gap-2.5">
                        <span className="tnum w-8 shrink-0 text-2xs text-muted">
                          {star} ★
                        </span>
                        <MiniBar
                          value={pct}
                          tone={star >= 4 ? 'good' : star === 3 ? 'warn' : 'bad'}
                          width={0}
                        />
                        <span className="tnum w-8 shrink-0 text-right text-2xs text-muted">
                          {count}
                        </span>
                      </div>
                    )
                  })}
                </div>

                {/* Izohlar */}
                <div className="space-y-1.5 border-t border-border/60 pt-3">
                  {feedback.data.items.filter((i) => i.comment).length === 0 ? (
                    <p className="py-2 text-center text-2xs text-muted">
                      {user?.role === 'sales'
                        ? t('agents.commentsRestricted')
                        : t('common.noData')}
                    </p>
                  ) : (
                    feedback.data.items
                      .filter((item) => item.comment)
                      .slice(0, 6)
                      .map((item) => (
                        <div
                          key={item.id}
                          className="rounded-xl bg-surface-2/60 p-3"
                        >
                          <div className="mb-1 flex items-center gap-2">
                            <span className="text-2xs text-warn">
                              {'★'.repeat(item.csat)}
                              <span className="text-muted">
                                {'★'.repeat(5 - item.csat)}
                              </span>
                            </span>
                            <span className="tnum text-2xs text-muted">
                              {fmt.date(item.responded_at)}
                            </span>
                          </div>
                          <p className="text-xs leading-relaxed">{item.comment}</p>
                        </div>
                      ))
                  )}
                </div>

                <p className="mt-3 flex items-center gap-1.5 text-2xs text-muted">
                  <Clock className="size-3" />
                  {t('agents.anonymous')}
                </p>
              </>
            )}
          </CardBody>
        </Card>
      </div>
    </Page>
  )
}

/* ── Client bahosi KPI ───────────────────────────────────────
   Uchta holat, uchtasi ham boshqacha ko'rinadi:

   • tayyor        → 4.25 / 5
   • yig'ilmoqda   → 1 / 5 + «yana 4 ta javob kerak»
   • javob yo'q    → «—» (bu yerda chiziq HALOL: haqiqatan hech narsa yo'q)

   Ilgari birinchi va ikkinchi holat bir xil «—» edi. Foydalanuvchi
   Telegramdan baho qo'yib, profilda chiziq ko'rdi va «ishlamayapti»
   deb xulosa qildi — u haq edi, chunki UI qoidani aytmagan.

   Chegara raqami KODGA YOZILMAYDI: `survey.min_responses` admin
   sozlamasi, `ratingProgress()` uni javobdan o'qiydi. */

function ClientRatingKpi({
  summary,
  loading,
  visible,
}: {
  summary: FeedbackSummary | undefined
  loading: boolean
  visible: boolean
}) {
  const { t } = useTranslation()
  const progress = ratingProgress(summary)
  const ready = Boolean(summary?.ready && summary.average != null)
  const collecting = visible && !ready && progress.count > 0

  /* «1 / 5» — javob KELGANI ham, nima kutilayotgani ham bitta raqamda.
     Chegara noma'lum bo'lsa maxraj tushib qoladi («1»), «1 / undefined»
     emas. */
  const value = ready
    ? summary!.average!.toFixed(2)
    : collecting
      ? progress.min != null
        ? `${progress.count} / ${progress.min}`
        : String(progress.count)
      : null

  return (
    <KpiCard
      icon={Star}
      label={t('kpi.clientRating')}
      value={value}
      // Maxraj qiymat ichida bo'lgani uchun «/ 5» faqat tayyor holatda
      suffix={ready ? '/ 5' : undefined}
      hint={
        collecting
          ? progress.remaining != null && progress.remaining > 0
            ? t('surveys.remainingShort', { count: progress.remaining })
            : t('kpi.ratingPending', { count: progress.count })
          : undefined
      }
      tone="warn"
      loading={loading}
    />
  )
}
