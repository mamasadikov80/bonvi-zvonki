/**
 * Qo'ng'iroq turi belgisi.
 *
 * ⚠️ NEGA BU EKRANDA BO'LISHI SHART. Faqat `sales` turidagi qo'ng'iroq
 * baholanadi — `internal` da ball BO'SH bo'ladi. Tur ko'rinmasa, menejer
 * bo'sh ballni «AI ishlamadi» deb o'qiydi va bejiz qayta baholashga
 * yuboradi. Tur ko'rinsa esa savol yo'q: «ichki suhbat — baholanmaydi».
 *
 * Ranglar ataylab BAHOLOVCHI emas: ichki suhbat «yomon» degani emas,
 * shunchaki boshqa turdagi ish. Faqat `sales` urg'ulanadi, chunki savdo
 * KPI'si shundan hisoblanadi.
 */

import { Briefcase, ShoppingCart } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { CallType } from '@/modules/calls/api'
import { Badge } from '@/shared/ui/primitives'

type Tone = 'accent' | 'neutral'

const LOOK: Record<CallType, { icon: typeof ShoppingCart; tone: Tone }> = {
  sales: { icon: ShoppingCart, tone: 'accent' },
  internal: { icon: Briefcase, tone: 'neutral' },
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

  // Eski yozuvda notanish qiymat bo'lishi mumkin (`service`,
  // `personal`) — u «ichki» ko'rinishida chiziladi: baholanmagani
  // aniq, aniq turi esa keyingi yurishda qaytadan qo'yiladi.
  const look = LOOK[type] ?? LOOK.internal
  const Icon = look.icon

  return (
    <Badge tone={look.tone} title={t(`calls.type.hint.${type}`, { defaultValue: '' })}>
      <Icon className="size-3" />
      {/* `defaultValue` — eski yozuvda notanish qiymat bo'lsa lug'at
          kalitining o'zi («calls.type.service») chiqib qolmasin */}
      {compact
        ? t(`calls.type.short.${type}`, { defaultValue: type })
        : t(`calls.type.${type}`, { defaultValue: type })}
    </Badge>
  )
}
