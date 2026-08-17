/**
 * Qo'ng'iroq turi belgisi.
 *
 * ⚠️ NEGA BU EKRANDA BO'LISHI SHART. Faqat `sales` turidagi qo'ng'iroq
 * baholanadi — qolganlarida ball BO'SH bo'ladi. Tur ko'rinmasa, menejer
 * bo'sh ballni «AI ishlamadi» deb o'qiydi va bejiz qayta baholashga
 * yuboradi. Tur ko'rinsa esa savol yo'q: «ichki suhbat — baholanmaydi».
 *
 * Ranglar ataylab BAHOLOVCHI emas: ichki yoki shaxsiy qo'ng'iroq
 * «yomon» degani emas, shunchaki boshqa turdagi ish. Faqat `sales`
 * urg'ulanadi, chunki savdo KPI'si shundan hisoblanadi.
 */

import { Briefcase, HelpCircle, Home, ShoppingCart, Wrench } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { CallType } from '@/modules/calls/api'
import { Badge } from '@/shared/ui/primitives'

type Tone = 'accent' | 'neutral'

const LOOK: Record<CallType, { icon: typeof ShoppingCart; tone: Tone }> = {
  sales: { icon: ShoppingCart, tone: 'accent' },
  service: { icon: Wrench, tone: 'neutral' },
  internal: { icon: Briefcase, tone: 'neutral' },
  personal: { icon: Home, tone: 'neutral' },
  unclear: { icon: HelpCircle, tone: 'neutral' },
}

export function CallTypeBadge({
  type,
  compact = false,
}: {
  type: CallType | null | undefined
  /** Jadvalda joy tor — faqat belgi va qisqa nom */
  compact?: boolean
}) {
  const { t } = useTranslation()
  // `null` — hali tasniflanmagan. Hech narsa ko'rsatmaymiz: «noma'lum»
  // deb yozib qo'yish bo'sh ogohlantirish bo'lardi.
  if (!type) return null

  const look = LOOK[type] ?? LOOK.unclear
  const Icon = look.icon

  return (
    <Badge tone={look.tone} title={t(`calls.type.hint.${type}`)}>
      <Icon className="size-3" />
      {compact ? t(`calls.type.short.${type}`) : t(`calls.type.${type}`)}
    </Badge>
  )
}
