import { useTranslation } from 'react-i18next'

import type { AgentRow } from '@/modules/analytics/api'
import { cn, formatDuration, scoreTone } from '@/shared/lib/utils'
import { Avatar, ScoreRing, TrendDelta } from '@/shared/ui/dataviz'
import { Skeleton } from '@/shared/ui/primitives'

const RANK_LABEL = ['#1 · Eng yaxshi', '#2', '#3']

export function TopPerformers({
  rows,
  loading,
}: {
  rows: AgentRow[] | undefined
  loading?: boolean
}) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="grid gap-3 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[132px] w-full" />
        ))}
      </div>
    )
  }

  const top = (rows ?? []).slice(0, 3)
  if (!top.length) return null

  return (
    <div className="grid gap-3 md:grid-cols-3">
      {top.map((row, index) => {
        const tone = scoreTone(row.ai_score) as 'accent' | 'good' | 'warn' | 'bad'
        return (
          <div
            key={row.agent_id}
            className={cn(
              'card p-4 transition-colors',
              index === 0 && 'ring-1 ring-accent/25',
            )}
          >
            <div className="flex items-center justify-between">
              <span className="label-eyebrow">{RANK_LABEL[index]}</span>
              <TrendDelta value={row.rank_delta} />
            </div>

            <div className="mt-3 flex items-center gap-3">
              <Avatar name={row.full_name} color={row.color} src={row.avatar_url} size="lg" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold">{row.full_name}</div>
                <div className="truncate text-2xs text-muted">{row.region}</div>
              </div>
              <ScoreRing value={row.ai_score} tone={tone} />
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-3">
              <Stat label={t('table.calls')} value={String(row.calls)} />
              <Stat
                label={t('kpi.clientRating')}
                value={
                  row.client_rating_ready && row.client_rating != null
                    ? `${row.client_rating.toFixed(1)} / 5`
                    : '—'
                }
              />
              <Stat
                label={t('table.duration')}
                value={formatDuration(row.avg_duration_sec)}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wide text-muted">{label}</div>
      <div className="tnum mt-0.5 text-sm font-semibold">{value}</div>
    </div>
  )
}
