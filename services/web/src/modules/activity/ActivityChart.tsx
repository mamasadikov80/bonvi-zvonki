/**
 * Kunlik qo'ng'iroq dinamikasi.
 *
 * Uchta qatlam: kiruvchi va chiquvchi — maydon (hajm), javobsiz —
 * qalin qizil chiziq. Javobsizni ham maydon qilish uni hajm ichida
 * yo'q qilardi: u 300 ga nisbatan 140 — ko'rinishi kerak, lekin
 * hajmning bir qismi sifatida emas, ALOHIDA ogohlantirish sifatida.
 *
 * ⚠️ Bu grafikda BAHO va REYTING yo'q va bo'lmaydi. Bu bo'lim faqat
 * qo'ng'iroq statistikasi uchun: hajm va javobgarlik. Sifat
 * ko'rsatkichlari boshqa bo'limda va ularni bir grafikka qo'shish
 * ikki xil o'lchov birligini (dona va ball) aralashtirardi.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTranslation } from 'react-i18next'

import type { ActivityDay } from '@/modules/activity/api'
import { EmptyState } from '@/shared/ui/primitives'

const AXIS = {
  stroke: 'hsl(var(--muted))',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const

export function ActivityChart({ data }: { data: ActivityDay[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  const rows = data.map((point) => ({
    ...point,
    // `dd.MM` — 30 kunda ham sig'adi, yil takrorlanishi ortiqcha
    label: point.day.slice(8, 10) + '.' + point.day.slice(5, 7),
  }))

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="inFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity={0.2} />
            <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="outFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--good))" stopOpacity={0.18} />
            <stop offset="100%" stopColor="hsl(var(--good))" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid
          stroke="hsl(var(--border))"
          strokeDasharray="3 3"
          vertical={false}
        />
        <XAxis dataKey="label" {...AXIS} minTickGap={20} />
        <YAxis {...AXIS} width={38} allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: 'hsl(var(--surface))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 12,
            fontSize: 12,
          }}
        />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
        <Area
          type="monotone"
          dataKey="inbound"
          name={t('activity.colIn')}
          stroke="hsl(var(--accent))"
          strokeWidth={2}
          fill="url(#inFill)"
        />
        <Area
          type="monotone"
          dataKey="outbound"
          name={t('activity.colOut')}
          stroke="hsl(var(--good))"
          strokeWidth={2}
          fill="url(#outFill)"
        />
        {/* Javobsiz — maydon EMAS, chiziq: hajmning qismi bo'lib
            ko'rinmasligi, alohida ogohlantirish bo'lishi kerak */}
        <Line
          type="monotone"
          dataKey="missed"
          name={t('activity.colMissed')}
          stroke="hsl(var(--bad))"
          strokeWidth={2.5}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
