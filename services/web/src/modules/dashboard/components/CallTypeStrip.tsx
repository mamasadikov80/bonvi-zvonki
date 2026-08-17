/**
 * Qo'ng'iroq turlari bo'yicha taqsimot — bitta yupqa qator.
 *
 * NEGA BU KERAK. KPI kartadagi «Qo'ng'iroqlar» soni faqat BAHOLANGAN,
 * ya'ni savdo suhbatlarini sanaydi (savdo bo'lmaganida baho qatori
 * ataylab yozilmaydi). Bu qator bo'lmasa menejer 69 ta qo'ng'iroq
 * bo'lgan davrda «6» degan raqamni ko'rib, qolgan 63 tasi qayerga
 * ketganini bilmaydi — tizim ma'lumot yo'qotgandek ko'rinadi.
 *
 * Shu sabab u KARTA emas, qator: bu ko'rsatkich emas, izoh. Ballga
 * ta'sir qilmaydigan sonlarni KPI qatoriga qo'yish ularni maqsad
 * qilib ko'rsatardi — «ichki suhbatni kamaytirish kerak» degan xulosa
 * chiqarilardi, holbuki ichki suhbat ham ish.
 */

import { useTranslation } from 'react-i18next'

import type { CallTypeCounts } from '@/modules/analytics/api'
import { cn, formatNumber } from '@/shared/lib/utils'

/** Ko'rsatish tartibi — savdo birinchi, «aniqlanmadi» oxirida.
 *  Alifbo tartibi ma'nosiz bo'lardi: savdo — asosiy tur. */
const ORDER: (keyof CallTypeCounts)[] = [
  'sales',
  'service',
  'internal',
  'personal',
  'unclear',
  'unknown',
]

const TONE: Partial<Record<keyof CallTypeCounts, string>> = {
  sales: 'bg-good',
}

export function CallTypeStrip({
  counts,
  loading,
}: {
  counts?: CallTypeCounts
  loading?: boolean
}) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-9 animate-pulse rounded-xl bg-surface-2/60" />
  }
  const total = counts ? ORDER.reduce((sum, key) => sum + (counts[key] || 0), 0) : 0
  // Ma'lumot yo'q davrda bo'sh qator chizish shovqin — umuman ko'rinmaydi
  if (!counts || total === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl bg-surface-2/50 px-3.5 py-2.5">
      <span className="text-2xs font-medium text-muted">
        {t('kpi.byType', { count: total })}
      </span>
      {ORDER.filter((key) => (counts[key] || 0) > 0).map((key) => (
        <span key={key} className="flex items-center gap-1.5 text-2xs">
          <span
            className={cn('size-1.5 rounded-full', TONE[key] ?? 'bg-muted/40')}
            aria-hidden
          />
          <span className="text-muted">
            {key === 'unknown' ? t('kpi.typeUnknown') : t(`calls.type.${key}`)}
          </span>
          <span className="tnum font-semibold">{formatNumber(counts[key])}</span>
        </span>
      ))}
    </div>
  )
}
