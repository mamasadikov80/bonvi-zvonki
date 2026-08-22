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
    /* ⚠️ `whitespace-nowrap` — MAJBURIY. Yorliq matni («Tekshirib
       bo'lmadi», «Действительно подозрительно») tor ustunda ikki-uch
       qatorga bo'linib, o'sha qatorni qo'shnilaridan uch barobar
       baland qilib qo'yardi. */
    <Badge tone={look.tone} className="shrink-0 whitespace-nowrap" title={hint}>
      <Icon className="size-3" />
      {t(`sales.verdict.${verdict}`, { defaultValue: verdict })}
    </Badge>
  )
}

/**
 * Nega tekshirib bo'lmadi — QISQA yorliq.
 *
 * To'liq jumla («Umumiy kod: bitta kod ostida ko'p mijoz…») katakda
 * paragrafga aylanib, qator balandligini uch barobar oshirardi.
 * Endi katakda ikki so'z turadi, to'lig'i esa maslahatnomada.
 */
export function SkipBadge({ reason }: { reason: SaleSkipReason }) {
  const { t } = useTranslation()

  return (
    <Badge
      tone="neutral"
      className="shrink-0 whitespace-nowrap"
      title={t(`sales.skip.${reason}`, { defaultValue: '' })}
    >
      {t(`sales.skipShort.${reason}`, { defaultValue: reason })}
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
  hints,
}: {
  rules: SaleRule[]
  /** R1 ning oynasi — «savdo kuni + oldingi N kun» */
  windowDays?: number
  /** Qoidaning DALILI — maslahatnomaga qo'shiladi («oldingi savdo
   *  qachon edi?»). Jadval katagida bunga joy yo'q, lekin savol
   *  yorliqni ko'rgan zahoti tug'iladi. */
  hints?: Partial<Record<SaleRule, string>>
}) {
  const { t } = useTranslation()
  /* Bo'sh ro'yxatda «—» YOZILMAYDI: u qatorni shovqin bilan
     to'ldiradi, holbuki yonidagi xulosa yorlig'i allaqachon
     «buzilgan qoida yo'q» deb turibdi. */
  if (!rules.length) return null

  return (
    <span className="inline-flex shrink-0 items-center gap-1">
      {rules.map((rule) => {
        const base =
          rule === 'R1' && windowDays
            ? t('sales.rule.R1window', { count: windowDays })
            : t(`sales.rule.${rule}`, { defaultValue: rule })
        const hint = hints?.[rule]

        return (
          <Badge
            key={rule}
            tone="warn"
            className="whitespace-nowrap"
            title={hint ? `${base} — ${hint}` : base}
          >
            {rule}
          </Badge>
        )
      })}
    </span>
  )
}

/**
 * Qoidalar izohi — jadval sarlavhasi ostidagi BITTA qator.
 *
 * ⚠️ IZOH JADVALDAN TASHQARIDA TURADI. Uni katakka yozib ko'rilgan
 * edi: tor ustunda «Oldingi savdo 19/08/2026 — orasida 0 ta suhbat»
 * degan matn to'rt qatorga o'ralib, bitta qatorni qo'shnilaridan uch
 * barobar baland qilib qo'ydi va jadval tishli bo'lib qoldi. Endi
 * katakda faqat KOD (`R1`), ma'nosi esa shu yerda — bir marta, hamma
 * qator uchun.
 *
 * ⚠️ Maslahatnomaga (`title`) tayanib bo'lmaydi: jadval `overflow-x`
 * konteyner ichida va sensorli ekranda maslahatnoma umuman
 * ochilmaydi. Uchta qisqa izoh esa bitta qatorga sig'adi.
 */
export function RuleLegend({ windowDays }: { windowDays?: number }) {
  const { t } = useTranslation()

  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs leading-relaxed text-muted">
      {(['R1', 'R2', 'R3'] as SaleRule[]).map((rule, index) => (
        <span key={rule} className="inline-flex items-center gap-1.5">
          {index > 0 && <span className="text-muted/40">·</span>}
          <span
            className="font-semibold text-warn"
            title={
              rule === 'R1' && windowDays
                ? t('sales.rule.R1window', { count: windowDays })
                : t(`sales.rule.${rule}`)
            }
          >
            {rule}
          </span>
          <span>— {t(`sales.ruleShort.${rule}`)}</span>
        </span>
      ))}
    </p>
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
      <Badge tone="accent" className="whitespace-nowrap">
        <CircleSlash className="size-3" />
        {t('sales.review.new')}
      </Badge>
    )
  }

  const justified = review.status === 'justified'
  return (
    <Badge
      tone={justified ? 'good' : 'bad'}
      className="whitespace-nowrap"
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
