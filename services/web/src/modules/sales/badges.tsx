/**
 * Savdo nazoratining belgilari: xulosa, qoida, qaror.
 *
 * ⚠️ RANGLAR AYBLAMAYDI. Shubhali savdo — qizil emas, SARIQ: bu
 * tekshirish uchun navbat, ayblov emas (shartnoma, 1-bo'lim).
 * Qizil faqat ODAM «haqiqatan shubhali» deb qaror qilgandan keyin
 * paydo bo'ladi — ya'ni rang tizimning taxminini emas, rahbarning
 * qarorini ko'rsatadi.
 *
 * `not_checkable` ham «toza» emas, kulrang: u SAP dagi ma'lumot
 * sifatining ko'rsatkichi va vaqt o'tib kamayishi kerak.
 */

import { CircleHelp, CircleSlash, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type {
  SaleReview,
  SaleRule,
  SaleSkipReason,
  SaleVerdict,
} from '@/modules/sales/api'
import { Badge } from '@/shared/ui/primitives'

type Tone = 'neutral' | 'accent' | 'good' | 'warn' | 'bad'

const VERDICT_LOOK: Record<SaleVerdict, { icon: typeof ShieldCheck; tone: Tone }> = {
  ok: { icon: ShieldCheck, tone: 'good' },
  suspicious: { icon: TriangleAlert, tone: 'warn' },
  not_checkable: { icon: CircleHelp, tone: 'neutral' },
}

export function VerdictBadge({
  verdict,
  skipReason,
}: {
  verdict: SaleVerdict
  /** Nega tekshirib bo'lmadi — maslahatnomada ochiq aytiladi */
  skipReason?: SaleSkipReason | null
}) {
  const { t } = useTranslation()
  // Notanish qiymat (backend yangi toifa qo'shsa) qatorni yiqitmaydi
  const look = VERDICT_LOOK[verdict] ?? VERDICT_LOOK.not_checkable
  const Icon = look.icon

  const hint =
    verdict === 'not_checkable' && skipReason
      ? t(`sales.skip.${skipReason}`, { defaultValue: '' })
      : t(`sales.verdictHint.${verdict}`, { defaultValue: '' })

  return (
    <Badge tone={look.tone} title={hint}>
      <Icon className="size-3" />
      {t(`sales.verdict.${verdict}`, { defaultValue: verdict })}
    </Badge>
  )
}

/**
 * Buzilgan qoidalar.
 *
 * Yorliqning o'zi qisqa (`R1`), ma'nosi esa maslahatnomada. Uzun
 * nomni jadvalga yozib bo'lmaydi — uchta qoida bitta katakka
 * sig'maydi; lekin ma'nosi YO'QOLMASIN desa, jadval tepasida doimiy
 * izoh qatori ham turadi (`RuleLegend`).
 */
export function RuleBadges({
  rules,
  windowDays,
}: {
  rules: SaleRule[]
  /** R1 ning oynasi — «savdo kuni + oldingi N kun» */
  windowDays?: number
}) {
  const { t } = useTranslation()
  if (!rules.length) return <span className="text-muted">—</span>

  return (
    <div className="flex flex-wrap gap-1">
      {rules.map((rule) => (
        <Badge
          key={rule}
          tone="warn"
          title={
            rule === 'R1' && windowDays
              ? t('sales.rule.R1window', { count: windowDays })
              : t(`sales.rule.${rule}`, { defaultValue: rule })
          }
        >
          {rule}
        </Badge>
      ))}
    </div>
  )
}

/**
 * Qoidalar izohi — jadvaldan TASHQARIDA, doimiy joyda.
 *
 * Maslahatnomaga tayanib bo'lmaydi: jadval `overflow-x` konteyner
 * ichida, sichqonchasiz (planshet) esa u umuman ochilmaydi. Uchta
 * qisqa satr ekranda joy yemaydi, lekin `R2` nima ekanini so'rash
 * ehtiyojini butunlay yo'q qiladi.
 */
export function RuleLegend({ windowDays }: { windowDays?: number }) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl bg-surface-2/50 px-3.5 py-2.5">
      {(['R1', 'R2', 'R3'] as SaleRule[]).map((rule) => (
        <span key={rule} className="flex items-center gap-1.5 text-2xs">
          <Badge tone="warn">{rule}</Badge>
          <span className="text-muted">
            {rule === 'R1' && windowDays
              ? t('sales.rule.R1window', { count: windowDays })
              : t(`sales.rule.${rule}`)}
          </span>
        </span>
      ))}
    </div>
  )
}

/**
 * Rahbarning qarori.
 *
 * `null` — hali ko'rilmagan. Bu BO'SH JOY emas, holat: shuning uchun
 * u ham yozib ko'rsatiladi, aks holda «qaror qo'yilmagan» va
 * «ma'lumot yuklanmadi» bir xil ko'rinardi.
 */
export function ReviewBadge({ review }: { review: SaleReview | null }) {
  const { t } = useTranslation()

  if (!review) {
    return (
      <Badge tone="accent">
        <CircleSlash className="size-3" />
        {t('sales.review.new')}
      </Badge>
    )
  }

  const justified = review.status === 'justified'
  return (
    <Badge
      tone={justified ? 'good' : 'bad'}
      title={review.note ?? undefined}
    >
      {justified ? (
        <ShieldCheck className="size-3" />
      ) : (
        <TriangleAlert className="size-3" />
      )}
      {t(`sales.review.${review.status}`, { defaultValue: review.status })}
    </Badge>
  )
}
