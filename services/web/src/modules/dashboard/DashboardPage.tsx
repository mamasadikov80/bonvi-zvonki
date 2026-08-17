import { AlertTriangle, Clock, Download, Phone, Star, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import {
  useAgentLeaderboard,
  useBlocks,
  useDistribution,
  useOverview,
  useRedFlags,
  useTrend,
  type AnalyticsQuery,
} from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import { AgentTable } from '@/modules/dashboard/components/AgentTable'
import {
  BlocksChart,
  DistributionChart,
  RedFlagChart,
  TrendChart,
} from '@/modules/dashboard/components/charts'
import { FilterBar } from '@/modules/dashboard/components/FilterBar'
import { CallTypeStrip } from '@/modules/dashboard/components/CallTypeStrip'
import { KpiCard } from '@/modules/dashboard/components/KpiCard'
import { TopPerformers } from '@/modules/dashboard/components/TopPerformers'
import { rangeDays, rangeToQuery, resolvePreset, type DateRange } from '@/shared/lib/date'
import { formatDuration, formatNumber } from '@/shared/lib/utils'
import { Page, PageHeader } from '@/shared/layout/Page'
import { Button, Card, CardBody, CardHeader, Skeleton } from '@/shared/ui/primitives'

export function DashboardPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [range, setRange] = useState<DateRange>(() => resolvePreset('last30'))
  const [query, setQuery] = useState<AnalyticsQuery>(() => rangeToQuery(resolvePreset('last30')))

  const isSales = user?.role === 'sales'

  const overview = useOverview(query)
  const trend = useTrend(query)
  const agents = useAgentLeaderboard(query)
  const blocks = useBlocks(query)
  const flags = useRedFlags(query)
  const distribution = useDistribution(query)

  // Sparkline ma'lumotlari trend javobidan olinadi
  const series = trend.data ?? []
  const sparkCalls = series.map((p) => p.calls)
  const sparkScore = series.map((p) => p.ai_score)
  const sparkRating = series.map((p) => p.client_rating)

  return (
    <Page>
      <PageHeader
        title={isSales ? (user?.full_name ?? '') : t('nav.dashboard')}
        subtitle={
          agents.data?.length
            ? t('dashboard.subtitle', {
                count: agents.data.length,
                days: rangeDays(range),
              })
            : t('app.tagline')
        }
        actions={
          <Button variant="secondary" size="sm">
            <Download className="size-3.5" />
            {t('common.export')}
          </Button>
        }
      />

      <FilterBar
        value={query}
        onChange={setQuery}
        range={range}
        onRangeChange={setRange}
        showAgentFilter={!isSales}
        showRegionFilter={!isSales}
      />

      {/* ── KPI kartalar ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-5 2xl:gap-4">
        <KpiCard
          icon={Phone}
          label={t('kpi.calls')}
          value={overview.data ? formatNumber(overview.data.calls.value ?? 0) : null}
          delta={overview.data?.calls.delta_percent}
          /* Bu son BAHOLANGANLARNI sanaydi. Izohsiz qoldirilsa menejer
             uni «jami qo'ng'iroq» deb o'qiydi va tizim ma'lumot
             yo'qotgandek ko'rinadi — aslida qolganlari savdo emas. */
          hint={
            overview.data && overview.data.calls_total > (overview.data.calls.value ?? 0)
              ? t('kpi.callsHint', { total: overview.data.calls_total })
              : undefined
          }
          spark={sparkCalls}
          loading={overview.isLoading}
        />
        <KpiCard
          icon={TrendingUp}
          label={t('kpi.aiScore')}
          value={overview.data?.ai_score.value ?? null}
          suffix="/ 100"
          delta={overview.data?.ai_score.delta_percent}
          spark={sparkScore}
          tone="good"
          loading={overview.isLoading}
        />
        {/* Reyting yetarli javob yig'ilmaguncha ko'rsatilmaydi — bitta
            mijozning kayfiyati xodimning bahosini belgilab qo'ymasin */}
        <KpiCard
          icon={Star}
          label={t('kpi.clientRating')}
          value={
            overview.data?.client_rating.ready
              ? overview.data.client_rating.value
              : null
          }
          suffix="/ 5"
          delta={
            overview.data?.client_rating.ready
              ? overview.data.client_rating.delta_percent
              : null
          }
          hint={
            overview.data && !overview.data.client_rating.ready
              ? t('kpi.ratingPending', {
                  count: overview.data.client_rating.count ?? 0,
                })
              : undefined
          }
          spark={sparkRating}
          tone="warn"
          loading={overview.isLoading}
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
        <KpiCard
          icon={Clock}
          label={t('kpi.avgDuration')}
          value={overview.data ? formatDuration(overview.data.avg_duration_sec) : null}
          loading={overview.isLoading}
        />
      </div>

      {/* Turlar taqsimoti — KPI qatoridan KEYIN va karta EMAS: bu
          ko'rsatkich emas, yuqoridagi songa izoh */}
      <CallTypeStrip counts={overview.data?.call_types} loading={overview.isLoading} />

      {/* ── Top-3 ─────────────────────────────────────────── */}
      {!isSales && <TopPerformers rows={agents.data} loading={agents.isLoading} />}

      {/* ── Trend ─────────────────────────────────────────── */}
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

      {/* ── Uch ustunli razrez ────────────────────────────── */}
      <div className="grid gap-3 lg:grid-cols-3 2xl:gap-4">
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

        <Card>
          <CardHeader title={t('chart.distribution')} />
          <CardBody className="pt-2">
            {distribution.isLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : (
              <DistributionChart data={distribution.data ?? []} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={t('chart.redFlagTypes')} />
          <CardBody className="pt-2">
            {flags.isLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : (
              <RedFlagChart data={flags.data ?? []} />
            )}
          </CardBody>
        </Card>
      </div>

      {/* ── Leaderboard ───────────────────────────────────── */}
      {!isSales && (
        <Card>
          <CardHeader
            title={t('dashboard.leaderboard', { defaultValue: 'Xodimlar reytingi' })}
          />
          <div className="mt-3">
            <AgentTable
              rows={agents.data}
              loading={agents.isLoading}
              onSelect={(id) => navigate(`/agents/${id}`)}
            />
          </div>
        </Card>
      )}
    </Page>
  )
}
