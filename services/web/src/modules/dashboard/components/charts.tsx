/**
 * Grafiklar — Recharts.
 *
 * Ranglar CSS o'zgaruvchilaridan olinadi, shuning uchun yorug'/qorong'i
 * mavzuda avtomatik moslashadi. Har grafik o'z konteynerida siljiydi.
 */

import { useTranslation } from 'react-i18next'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type {
  BlockRow,
  DistributionRow,
  RedFlagRow,
  TrendPoint,
} from '@/modules/analytics/api'
import { formatShortDate } from '@/shared/lib/date'
import { EmptyState } from '@/shared/ui/primitives'

const AXIS = {
  stroke: 'hsl(var(--muted))',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
}

/* Recharts `content={<ChartTooltip />}` orqali proplarni O'ZI uzatadi,
   shuning uchun hammasi ixtiyoriy. Ilgari bu yerda `any` turardi —
   `entry.color` xato yozilsa ham hech kim aytmasdi. */
interface TooltipEntry {
  dataKey?: string | number
  name?: string
  value?: number | string | null
  color?: string
  fill?: string
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string | number
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2 shadow-lg">
      <div className="mb-1 text-2xs font-medium text-muted">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-xs">
          <span
            className="size-2 rounded-full"
            style={{ background: entry.color ?? entry.fill }}
          />
          <span className="text-muted">{entry.name}:</span>
          <span className="tnum font-medium text-text">{entry.value ?? '—'}</span>
        </div>
      ))}
    </div>
  )
}

/* ── 1. Trend: AI bahosi vs client bahosi ────────────────── */

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  // Client bahosi 1–5 → bitta o'qda ko'rsatish uchun 100 ballikka keltiriladi
  const rows = data.map((point) => ({
    ...point,
    client_scaled:
      point.client_rating != null ? Math.round((point.client_rating / 5) * 100) : null,
    label: formatShortDate(point.date),
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      {/* ⚠️ `left` MANFIY EMAS. Ilgari `-20` turardi va u grafikni
          chapga surib, Y o'qidagi eng katta yorliqni kesib tashlardi:
          «100» o'rniga «00» ko'rinardi. Bo'sh joyni yutish uchun
          o'qning o'z kengligi (`width`) sozlanadi — chekka emas. */}
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="aiFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity={0.22} />
            <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" {...AXIS} minTickGap={24} />
        {/* Uch xonali «100» sig'ishi uchun kamida shuncha kerak */}
        <YAxis domain={[0, 100]} {...AXIS} width={34} />
        <Tooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="ai_score"
          name={t('chart.aiScore')}
          stroke="hsl(var(--accent))"
          strokeWidth={2}
          fill="url(#aiFill)"
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="client_scaled"
          name={t('chart.clientRating')}
          stroke="hsl(var(--good))"
          strokeWidth={2}
          strokeDasharray="4 4"
          dot={false}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ── 2. Ball taqsimoti ───────────────────────────────────── */

export function DistributionChart({ data }: { data: DistributionRow[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  const tone = (range: string) => {
    const low = Number(range.split('–')[0])
    if (low >= 85) return 'hsl(var(--good))'
    if (low >= 70) return 'hsl(var(--accent))'
    if (low >= 55) return 'hsl(var(--warn))'
    return 'hsl(var(--bad))'
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="range" {...AXIS} />
        {/* Qo'ng'iroqlar soni to'rt xonagacha o'sishi mumkin */}
        <YAxis {...AXIS} width={40} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'hsl(var(--surface-2))' }} />
        <Bar dataKey="count" name={t('chart.calls')} radius={[4, 4, 0, 0]}>
          {data.map((row) => (
            <Cell key={row.range} fill={tone(row.range)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── 3. Rubrika bloklari (radar) ─────────────────────────── */

export function BlocksChart({ data }: { data: BlockRow[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  return (
    <ResponsiveContainer width="100%" height={220}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="hsl(var(--border))" />
        <PolarAngleAxis dataKey="label" tick={{ fill: 'hsl(var(--muted))', fontSize: 10 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Tooltip content={<ChartTooltip />} />
        <Radar
          dataKey="percent"
          name={t('chart.blocks')}
          stroke="hsl(var(--accent))"
          fill="hsl(var(--accent))"
          fillOpacity={0.2}
          strokeWidth={2}
        />
      </RadarChart>
    </ResponsiveContainer>
  )
}

/* ── 4. Qoidabuzarliklar (gorizontal ustun) ──────────────── */

export function RedFlagChart({ data }: { data: RedFlagRow[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  return (
    <ResponsiveContainer width="100%" height={Math.max(140, data.length * 34)}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
      >
        <XAxis type="number" {...AXIS} hide />
        <YAxis
          type="category"
          dataKey="label"
          {...AXIS}
          width={150}
          tick={{ fill: 'hsl(var(--muted))', fontSize: 11 }}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'hsl(var(--surface-2))' }} />
        <Bar
          dataKey="count"
          name={t('kpi.redFlags')}
          fill="hsl(var(--bad))"
          radius={[0, 4, 4, 0]}
          barSize={16}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
