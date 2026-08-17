/**
 * Qo'ng'iroq dinamikasi — BITTA grafik, ikki kesim.
 *
 * KESIM AVTOMATIK TANLANADI:
 *   · davr bir kundan uzun  → KUNLAR bo'yicha;
 *   · aynan bir kun         → SOATLAR bo'yicha.
 *
 * Nega avtomatik. Ilgari ikki alohida grafik turardi va bir kunlik davr
 * tanlanganda «kunlik dinamika» bitta nuqta bo'lib qolardi — mutlaqo
 * foydasiz. Ikkinchi grafik esa har doim soatlarni ko'rsatib, uzun
 * davrda soatlarni butun oy bo'ylab yig'ib berardi. Ya'ni har bir
 * holatda ikkitadan bittasi keraksiz edi. Endi kesim davrga o'zi
 * moslashadi va ekranda faqat ma'noli narsa qoladi.
 *
 * CHIZIQLARNI YOQIB-O'CHIRISH. To'rt qator bir vaqtda ko'rsatilsa
 * grafik o'qilmaydi (kiruvchi ~500, javobsiz ~140 — masshtab farqi
 * katta). Shuning uchun sukut bo'yicha hajm qatorlari yoniq,
 * muammo qatorlari esa tanlanadi. Yorliqni bosish — yoqish/o'chirish.
 *
 * ⚠️ Bu grafikda BAHO va REYTING yo'q va bo'lmaydi: bo'lim faqat
 * qo'ng'iroq statistikasi uchun. Dona va ball bir o'qda ko'rsatilsa
 * ikkisi ham ma'nosini yo'qotardi.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { ActivityDay, ActivityHour } from '@/modules/activity/api'
import { cn } from '@/shared/lib/utils'
import { EmptyState } from '@/shared/ui/primitives'

const AXIS = {
  stroke: 'hsl(var(--muted))',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const

type SeriesKey = 'inbound' | 'outbound' | 'missed' | 'outbound_no_answer'

interface Series {
  key: SeriesKey
  labelKey: string
  color: string
  /** Maydon sifatida chiziladimi (hajm) yoki chiziq bilan (muammo) */
  area: boolean
  /** Sukut bo'yicha ko'rinadimi */
  on: boolean
}

/** Qatorlar tartibi va ko'rinishi.
 *
 *  Hajm qatorlari (kiruvchi/chiquvchi) — maydon, sukut bo'yicha yoniq.
 *  Muammo qatorlari — chiziq, sukut bo'yicha O'CHIQ: ular hajmdan
 *  ancha kichik va birga chizilganda ikkalasi ham o'qilmay qoladi.
 *  «Javobsiz» yoniq qoldirildi, chunki u hisobotning asosiy mavzusi. */
const SERIES: Series[] = [
  { key: 'inbound', labelKey: 'activity.colIn', color: 'accent', area: true, on: true },
  { key: 'outbound', labelKey: 'activity.colOut', color: 'good', area: true, on: true },
  { key: 'missed', labelKey: 'activity.colMissed', color: 'bad', area: false, on: true },
  {
    key: 'outbound_no_answer',
    labelKey: 'activity.colOutNoAnswer',
    color: 'warn',
    area: false,
    on: false,
  },
]

export function CallsChart({
  days,
  hours,
  byHour,
}: {
  days: ActivityDay[]
  hours: ActivityHour[]
  /** `true` — soatlar kesimi (davr aynan bir kun) */
  byHour: boolean
}) {
  const { t } = useTranslation()
  const [hidden, setHidden] = useState<Set<SeriesKey>>(
    () => new Set(SERIES.filter((s) => !s.on).map((s) => s.key)),
  )

  const toggle = (key: SeriesKey) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const rows = byHour
    ? hours.map((point) => ({ ...point, label: String(point.hour).padStart(2, '0') }))
    : days.map((point) => ({
        ...point,
        // `dd.MM` — 30 kunda ham sig'adi
        label: `${point.day.slice(8, 10)}.${point.day.slice(5, 7)}`,
      }))

  if (!rows.length) return <EmptyState message={t('common.noData')} />

  return (
    <div>
      {/* Yorliqlar — Recharts `Legend` emas: bosilishi va o'chirilgan
          holati aniq ko'rinishi kerak, standart yorliq esa faqat
          shaffoflik bilan belgilaydi va u sezilmaydi */}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {SERIES.map((series) => {
          const off = hidden.has(series.key)
          return (
            <button
              key={series.key}
              onClick={() => toggle(series.key)}
              className={cn(
                'flex items-center gap-1.5 text-2xs font-medium transition-opacity',
                off ? 'opacity-35' : 'opacity-100',
              )}
              aria-pressed={!off}
            >
              <span
                className={cn(
                  'h-0.5 w-4 rounded-full',
                  off && 'opacity-40',
                )}
                style={{ background: `hsl(var(--${series.color}))` }}
                aria-hidden
              />
              <span className={off ? 'line-through' : undefined}>
                {t(series.labelKey)}
              </span>
            </button>
          )
        })}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            {SERIES.filter((s) => s.area).map((s) => (
              <linearGradient key={s.key} id={`fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={`hsl(var(--${s.color}))`} stopOpacity={0.2} />
                <stop offset="100%" stopColor={`hsl(var(--${s.color}))`} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid
            stroke="hsl(var(--border))"
            strokeDasharray="3 3"
            vertical={false}
          />
          <XAxis dataKey="label" {...AXIS} minTickGap={byHour ? 8 : 20} />
          <YAxis {...AXIS} width={40} allowDecimals={false} />
          <Tooltip
            contentStyle={{
              background: 'hsl(var(--surface))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 12,
              fontSize: 12,
            }}
            labelFormatter={(label) =>
              byHour ? t('activity.hourLabel', { hour: label }) : String(label)
            }
          />
          {/* Recharts `Legend` yashiriladi — o'z yorliqlarimiz yuqorida.
              Butunlay olib tashlansa balandlik hisobi o'zgarib, grafik
              pastdan kesilardi. */}
          <Legend content={() => null} />

          {SERIES.map((series) =>
            hidden.has(series.key) ? null : series.area ? (
              <Area
                key={series.key}
                type="monotone"
                dataKey={series.key}
                name={t(series.labelKey)}
                stroke={`hsl(var(--${series.color}))`}
                strokeWidth={2}
                fill={`url(#fill-${series.key})`}
              />
            ) : (
              <Line
                key={series.key}
                type="monotone"
                dataKey={series.key}
                name={t(series.labelKey)}
                stroke={`hsl(var(--${series.color}))`}
                strokeWidth={2.5}
                dot={rows.length <= 31 ? { r: 2 } : false}
              />
            ),
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
