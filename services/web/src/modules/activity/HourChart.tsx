/**
 * Soatlik razrez — kun bo'ylab yuklama va javobsizlar foizi.
 *
 * Ustunlar: kiruvchi qo'ng'iroqlar soni (chap o'q). Chiziq: javobsizlar
 * FOIZI (o'ng o'q). Ikki o'q kerak, chunki ular boshqa birlikda: 1300
 * dona va 35 foiz bitta o'qda ko'rsatilsa foiz nolga yopishib qolardi.
 *
 * ⚠️ Bu grafik rahbarga eng amaliy xulosani beradi: o'lchandi, tushlik
 * payti (12:00) javobsizlar 35%, ertalab 07:00 da 74%, kechqurun 19:00
 * da 40% — kunlik o'rtacha esa 29%. Ya'ni o'rtacha son bu tafovutni
 * yashirardi va «smenani qayta taqsimlash kerak» degan qarorga olib
 * kelmasdi.
 *
 * Baho va reyting bu yerda YO'Q: bo'lim faqat qo'ng'iroq statistikasi.
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTranslation } from 'react-i18next'

import type { ActivityHour } from '@/modules/activity/api'
import { EmptyState } from '@/shared/ui/primitives'

const AXIS = {
  stroke: 'hsl(var(--muted))',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const

/** Foiz ko'rsatiladigan eng kichik hajm.
 *
 *  Kechasi ikkita qo'ng'iroqdan bittasi javobsiz bo'lsa 50% chiqadi va
 *  grafikda eng yomon soat bo'lib turadi — bu ma'lumot emas, shovqin.
 *  Hajm ustuni esa baribir ko'rinadi, ya'ni ma'lumot yashirilmaydi. */
const MIN_VOLUME = 20

export function HourChart({ data }: { data: ActivityHour[] }) {
  const { t } = useTranslation()
  if (!data.length) return <EmptyState message={t('common.noData')} />

  const rows = data.map((point) => ({
    ...point,
    label: String(point.hour).padStart(2, '0'),
    // Kam hajmli soatda foiz chizilmaydi (`null` → chiziq uziladi)
    rate: point.inbound >= MIN_VOLUME ? point.missed_rate : null,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid
          stroke="hsl(var(--border))"
          strokeDasharray="3 3"
          vertical={false}
        />
        <XAxis dataKey="label" {...AXIS} />
        <YAxis yAxisId="count" {...AXIS} width={38} allowDecimals={false} />
        <YAxis
          yAxisId="rate"
          orientation="right"
          {...AXIS}
          width={38}
          domain={[0, 100]}
          unit="%"
        />
        <Tooltip
          contentStyle={{
            background: 'hsl(var(--surface))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 12,
            fontSize: 12,
          }}
        />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
        <Bar
          yAxisId="count"
          dataKey="inbound"
          name={t('activity.colIn')}
          fill="hsl(var(--accent))"
          fillOpacity={0.25}
          radius={[4, 4, 0, 0]}
        />
        <Line
          yAxisId="rate"
          type="monotone"
          dataKey="rate"
          name={t('activity.missedRateLabel')}
          stroke="hsl(var(--bad))"
          strokeWidth={2.5}
          dot={{ r: 2.5 }}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
