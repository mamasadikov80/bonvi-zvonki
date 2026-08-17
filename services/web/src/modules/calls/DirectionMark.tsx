/**
 * Yo'nalish va javob holati belgisi.
 *
 * NEGA IKKISI BIRGA. Ular birgalikda bitta ma'no beradi va alohida
 * ustunlarga bo'lish jadvalni kengaytirib, o'qishni qiyinlashtirardi:
 *
 *   ↗ chiquvchi + javob      — xodim qo'ng'iroq qildi, gaplashdi
 *   ↗ chiquvchi + javobsiz   — mijoz ko'tarmadi (xodimning aybi EMAS)
 *   ↙ kiruvchi  + javob      — mijoz murojaat qildi, javob berildi
 *   ↙ kiruvchi  + javobsiz   — «propushenniy», KOMPANIYA javob bermadi
 *
 * Faqat oxirgisi qizil bo'ladi. Chiquvchi javobsizni ham qizil qilish
 * xodimni nohaq ayblardi: mijoz band bo'lishi yoki telefoni o'chiq
 * bo'lishi mumkin, bunga xodim javobgar emas. O'lchandi — bu ikki
 * holat deyarli teng ko'p uchraydi (7 kunda 983 va 1047), ya'ni
 * ularni bir xil ko'rsatish qizil belgilarni ikki barobar oshirardi.
 */

import { ArrowDownLeft, ArrowUpRight, PhoneMissed } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { Direction } from '@/modules/calls/api'
import { cn } from '@/shared/lib/utils'

export function DirectionMark({
  direction,
  answered,
  className,
}: {
  direction: Direction
  answered: boolean | null
  className?: string
}) {
  const { t } = useTranslation()
  const inbound = direction === 'inbound'
  /* Faqat KIRUVCHI javobsiz «o'tkazib yuborilgan» hisoblanadi */
  const missed = inbound && answered === false

  const Icon = missed ? PhoneMissed : inbound ? ArrowDownLeft : ArrowUpRight
  const label = missed
    ? t('calls.direction.missed')
    : t(`calls.direction.${direction}`)

  return (
    <span
      title={
        answered === null
          ? `${label} · ${t('calls.direction.unknown')}`
          : label
      }
      className={cn(
        'inline-flex size-6 shrink-0 items-center justify-center rounded-lg',
        missed
          ? 'bg-bad/10 text-bad'
          : answered === false
            // Chiquvchi javobsiz — kulrang, ayblov emas
            ? 'bg-surface-2 text-muted'
            : inbound
              ? 'bg-accent-soft text-accent'
              : 'bg-good/10 text-good',
        className,
      )}
      aria-label={label}
    >
      <Icon className="size-3.5" />
    </span>
  )
}
