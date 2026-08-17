import { AlertTriangle, ChevronRight, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { AgentRow } from '@/modules/analytics/api'
import { cn, formatDuration, formatNumber, scoreTone, TONE_CLASS } from '@/shared/lib/utils'
import { Avatar, MiniBar, TrendDelta } from '@/shared/ui/dataviz'
import { Badge, EmptyState, Skeleton } from '@/shared/ui/primitives'

const MIN_RESPONSES = 5

type SortKey = 'ai_score' | 'calls' | 'client_rating' | 'red_flags'

const SORTS: { key: SortKey; labelKey: string }[] = [
  { key: 'ai_score', labelKey: 'table.aiScore' },
  { key: 'calls', labelKey: 'table.calls' },
  { key: 'client_rating', labelKey: 'table.clientRating' },
  { key: 'red_flags', labelKey: 'table.redFlags' },
]

export function AgentTable({
  rows,
  loading,
  onSelect,
}: {
  rows: AgentRow[] | undefined
  loading?: boolean
  onSelect?: (agentId: string) => void
}) {
  const { t } = useTranslation()
  const [sort, setSort] = useState<SortKey>('ai_score')

  if (loading) {
    return (
      <div className="space-y-2 p-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    )
  }

  if (!rows?.length) return <EmptyState message={t('table.empty')} />

  const sorted = [...rows].sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1))

  return (
    <>
      {/* Saralash tablari */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3">
        <p className="text-xs text-muted">
          {t('table.sortHint', { defaultValue: "Tafsilot uchun xodim ustiga bosing." })}
        </p>
        <div className="flex items-center gap-2">
          <span className="text-2xs text-muted">
            {t('table.sortBy', { defaultValue: 'Saralash' })}
          </span>
          <div className="flex items-center rounded-md border border-border p-0.5">
            {SORTS.map((option) => (
              <button
                key={option.key}
                onClick={() => setSort(option.key)}
                className={cn(
                  'rounded px-2.5 py-1 text-2xs font-medium transition-colors',
                  sort === option.key
                    ? 'bg-accent-soft text-accent'
                    : 'text-muted hover:text-text',
                )}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="scroll-x border-t border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="w-12 px-4 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                #
              </th>
              <th className="px-2 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                {t('table.agent')}
              </th>
              <th className="px-4 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                {t('table.region')}
              </th>
              {['table.calls', 'table.aiScore', 'table.clientRating', 'table.divergence', 'table.redFlags', 'table.duration'].map(
                (key) => (
                  <th
                    key={key}
                    className="px-4 py-2.5 text-right text-2xs font-medium uppercase tracking-wider text-muted"
                  >
                    {t(key)}
                  </th>
                ),
              )}
              <th className="w-10 px-2 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => {
              const tone = scoreTone(row.ai_score) as
                | 'accent'
                | 'good'
                | 'warn'
                | 'bad'
              return (
                <tr
                  key={row.agent_id}
                  onClick={() => onSelect?.(row.agent_id)}
                  className={cn(
                    'border-b border-border/60 transition-colors last:border-0',
                    onSelect && 'cursor-pointer hover:bg-surface-2/60',
                  )}
                >
                  {/* O'rin */}
                  <td className="tnum px-4 py-3 text-2xs text-muted">
                    {String(index + 1).padStart(2, '0')}
                  </td>

                  {/* Xodim */}
                  <td className="px-2 py-3">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={row.full_name} color={row.color} src={row.avatar_url} size="sm" />
                      <span className="font-medium">{row.full_name}</span>
                    </div>
                  </td>

                  <td className="px-4 py-3">
                    <Badge>{row.region}</Badge>
                  </td>

                  <td className="tnum px-4 py-3 text-right text-muted">
                    {formatNumber(row.calls)}
                  </td>

                  {/* AI ball + bar */}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <span className={cn('tnum font-semibold', TONE_CLASS[tone])}>
                        {row.ai_score?.toFixed(1) ?? '—'}
                      </span>
                      <MiniBar value={row.ai_score} tone={tone} />
                    </div>
                  </td>

                  {/* Client bahosi */}
                  <td className="px-4 py-3 text-right">
                    {row.client_rating_ready && row.client_rating != null ? (
                      <span className="tnum font-medium">
                        {row.client_rating.toFixed(1)}
                        <span className="ml-0.5 text-warn">★</span>
                      </span>
                    ) : (
                      <span className="text-2xs text-muted">
                        {t('table.collecting', {
                          count: row.client_rating_count,
                          min: MIN_RESPONSES,
                        })}
                      </span>
                    )}
                  </td>

                  {/* Divergensiya */}
                  <td className="px-4 py-3 text-right">
                    {row.divergence == null ? (
                      <span className="text-muted">—</span>
                    ) : row.divergence_flag ? (
                      <Badge tone="bad" title={t('divergence.warning')}>
                        <TriangleAlert className="size-3" />
                        <span className="tnum">
                          {row.divergence > 0 ? '+' : ''}
                          {row.divergence}
                        </span>
                      </Badge>
                    ) : (
                      <span className="tnum text-muted">
                        {row.divergence > 0 ? '+' : ''}
                        {row.divergence}
                      </span>
                    )}
                  </td>

                  {/* Qoidabuzarlik */}
                  <td className="px-4 py-3 text-right">
                    {row.red_flags > 0 ? (
                      <Badge tone="warn">
                        <AlertTriangle className="size-3" />
                        <span className="tnum">{row.red_flags}</span>
                      </Badge>
                    ) : (
                      <span className="text-muted">0</span>
                    )}
                  </td>

                  {/* Davomiylik + trend */}
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2.5">
                      <span className="tnum text-muted">
                        {formatDuration(row.avg_duration_sec)}
                      </span>
                      <TrendDelta value={row.rank_delta} />
                    </div>
                  </td>

                  <td className="px-2 py-3 text-muted">
                    {onSelect && <ChevronRight className="size-4" />}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
