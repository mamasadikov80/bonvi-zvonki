/**
 * Qaror modali — tekshiruv navbatining butun ma'nosi shu yerda.
 *
 * QOIDA: har qanday amal modalda (`SyncModal` bilan bir xil sabab).
 * Bu yerda qo'shimcha sabab bor: qaror qo'yish uchun DALIL kerak, u
 * esa jadval qatoriga sig'maydi. Modal ochilganda rahbar oldida
 * savdoning o'zi ham, unga qarshi dalil ham turadi.
 *
 * ⚠️ Ikki qarorning talabi TURLICHA:
 *   · «Oqlandi» — SABAB majburiy. «Oqladim» degan yozuv sababsiz
 *     hech narsa bermaydi; statistikaning ma'nosi esa aynan sabablar
 *     taqsimotida («savdolarning yarmi Telegram orqali kelishilgan»
 *     — bu tizimning kamchiligi, xodimning emas).
 *   · «Haqiqatan shubhali» — IZOH majburiy. Bu qaror odam uchun
 *     oqibatli bo'ladi, shuning uchun u bir bosishda qo'yilmasin.
 */

import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  REVIEW_REASONS,
  useReviewSale,
  type ComplianceRow,
  type SaleReviewReason,
  type SaleReviewStatus,
} from '@/modules/sales/api'
import { RuleBadges, VerdictBadge } from '@/modules/sales/badges'
import { ApiError } from '@/shared/api/client'
import { formatFullDate, formatFullDateTime } from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Button, Label, Select } from '@/shared/ui/primitives'

const NOTE_LIMIT = 500

export function ReviewModal({
  sale,
  windowDays,
  onClose,
}: {
  /** `null` — modal yopiq */
  sale: ComplianceRow | null
  windowDays?: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const review = useReviewSale()

  const [status, setStatus] = useState<SaleReviewStatus>('justified')
  const [reason, setReason] = useState<SaleReviewReason>('walk_in')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  /* Har ochilishda holat qaytadan tiklanadi. Mavjud qaror bo'lsa —
     o'sha qiymatlar bilan: rahbar ko'pincha izohni TUZATISH uchun
     qaytadan ochadi, bo'sh forma esa uni qayta yozishga majburlardi. */
  useEffect(() => {
    if (!sale) return
    setStatus(sale.review?.status ?? 'justified')
    setReason(sale.review?.reason ?? 'walk_in')
    setNote(sale.review?.note ?? '')
    setError(null)
    review.reset()
    // `review` har renderda yangi obyekt — kuzatilsa sikl bo'lardi
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sale?.id])

  const justified = status === 'justified'
  const valid = justified ? Boolean(reason) : note.trim().length >= 3

  const submit = () => {
    if (!sale || !valid) return
    setError(null)
    review.mutate(
      {
        saleId: sale.id,
        status,
        reason: justified ? reason : null,
        note: note.trim() || null,
      },
      {
        onSuccess: onClose,
        onError: (e) =>
          setError(e instanceof ApiError ? e.message : t('common.error')),
      },
    )
  }

  return (
    <Modal
      open={sale !== null}
      onOpenChange={(open) => !open && onClose()}
      title={t('sales.decision.title')}
      description={
        sale
          ? [sale.partner_name, sale.partner_code].filter(Boolean).join(' · ')
          : undefined
      }
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={review.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={justified ? 'primary' : 'danger'}
            disabled={!valid || review.isPending}
            onClick={submit}
          >
            {review.isPending ? t('sales.decision.saving') : t('sales.decision.save')}
          </Button>
        </>
      }
    >
      {sale && (
        <div className="space-y-5">
          <Evidence sale={sale} windowDays={windowDays} />

          {/* ── Qaror ────────────────────────────────────────
              Ikki tugma, `Segmented` emas: bular teng qiymatli
              ko'rinishlar emas, ikkita HAR XIL oqibatli qaror.
              Ikonka va rang bilan ajratilgani ataylab. */}
          <div>
            <Label>{t('sales.decision.question')}</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              <ChoiceButton
                active={justified}
                tone="good"
                icon={ShieldCheck}
                title={t('sales.review.justified')}
                hint={t('sales.decision.justifiedHint')}
                onClick={() => setStatus('justified')}
              />
              <ChoiceButton
                active={!justified}
                tone="bad"
                icon={AlertTriangle}
                title={t('sales.review.confirmed')}
                hint={t('sales.decision.confirmedHint')}
                onClick={() => setStatus('confirmed')}
              />
            </div>
          </div>

          {justified && (
            <div className="animate-scale-in">
              <Label>{t('sales.decision.reason')}</Label>
              <Select
                value={reason}
                onChange={(e) => setReason(e.target.value as SaleReviewReason)}
              >
                {REVIEW_REASONS.map((value) => (
                  <option key={value} value={value}>
                    {t(`sales.reason.${value}`)}
                  </option>
                ))}
              </Select>
              <p className="mt-1.5 text-2xs text-muted">
                {t('sales.decision.reasonHint')}
              </p>
            </div>
          )}

          <div>
            <Label>
              {justified ? t('sales.decision.note') : t('sales.decision.noteRequired')}
            </Label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value.slice(0, NOTE_LIMIT))}
              rows={3}
              placeholder={t('sales.decision.notePlaceholder')}
              className={cn(
                'w-full resize-y rounded-xl bg-surface-2 px-3.5 py-3 text-xs leading-relaxed',
                'ring-1 ring-inset ring-border',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
              )}
            />
            <p className="mt-1 text-2xs text-muted">
              {t('sales.decision.noteCount', { count: note.length, limit: NOTE_LIMIT })}
            </p>
          </div>

          {sale.review && (
            <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
              {t('sales.decision.previous', {
                who: sale.review.reviewed_by ?? '—',
                when: sale.review.reviewed_at
                  ? formatFullDateTime(sale.review.reviewed_at)
                  : '—',
              })}
            </p>
          )}

          {error && (
            <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs text-bad">
              {error}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}

/* ── Dalil ────────────────────────────────────────────────────
   Qaror faktlarga qarab qo'yiladi, shuning uchun ular modalda ham
   TO'LIQ turadi — jadvalga qaytib qarashga hojat qolmasin. */

function Evidence({
  sale,
  windowDays,
}: {
  sale: ComplianceRow
  windowDays?: number
}) {
  const { t } = useTranslation()

  const facts: { label: string; value: string; tone?: 'warn' | 'bad' }[] = [
    { label: t('sales.col.date'), value: formatFullDate(`${sale.occurred_on}T00:00:00`) },
    {
      label: t('sales.col.amountUsd'),
      value:
        sale.amount_usd != null ? `${formatNumber(Math.round(sale.amount_usd))} $` : '—',
    },
    {
      label: t('sales.col.branch'),
      value: [sale.branch, sale.agent_name ?? t('sales.noAgent')]
        .filter(Boolean)
        .join(' · '),
    },
    { label: t('sales.col.phone'), value: sale.phone ?? '—' },
    {
      label: t('sales.col.lastCall'),
      value: sale.last_call_at
        ? [
            formatFullDateTime(sale.last_call_at),
            sale.last_call_agent,
            sale.days_before != null
              ? t('sales.daysBefore', { count: sale.days_before })
              : null,
          ]
            .filter(Boolean)
            .join(' · ')
        : t('sales.noCallEver'),
      tone: sale.last_call_at ? undefined : 'bad',
    },
    {
      label: t('sales.col.previousSale'),
      value: sale.previous_sale_on
        ? t('sales.betweenCalls', {
            date: formatFullDate(`${sale.previous_sale_on}T00:00:00`),
            count: sale.calls_between,
          })
        : t('sales.noPreviousSale'),
      tone: sale.previous_sale_on && sale.calls_between === 0 ? 'warn' : undefined,
    },
    {
      label: t('sales.col.callsTotal'),
      value: t('sales.callsTotal', { count: sale.calls_total }),
      tone: sale.calls_total === 0 ? 'bad' : undefined,
    },
    { label: t('sales.col.operation'), value: sale.external_id },
  ]

  return (
    <div className="rounded-2xl bg-surface-2/60 p-3.5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={sale.verdict} skipReason={sale.skip_reason} />
        <RuleBadges rules={sale.broken_rules} windowDays={windowDays} />
      </div>
      <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
        {facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className="text-2xs text-muted">{fact.label}</dt>
            <dd
              className={cn(
                'text-xs',
                fact.tone === 'bad' && 'font-medium text-bad',
                fact.tone === 'warn' && 'font-medium text-warn',
              )}
            >
              {fact.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/* ── Tanlov tugmasi ───────────────────────────────────────── */

function ChoiceButton({
  active,
  tone,
  icon: Icon,
  title,
  hint,
  onClick,
}: {
  active: boolean
  tone: 'good' | 'bad'
  icon: typeof ShieldCheck
  title: string
  hint: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'flex items-start gap-2.5 rounded-xl p-3 text-left',
        'ring-1 ring-inset transition-all duration-250 ease-ios active:scale-[0.98]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
        active
          ? tone === 'good'
            ? 'bg-good/10 ring-good/40'
            : 'bg-bad/10 ring-bad/40'
          : 'bg-surface-2 ring-border hover:ring-border/80',
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          active ? (tone === 'good' ? 'text-good' : 'text-bad') : 'text-muted',
        )}
      />
      <span className="min-w-0">
        <span
          className={cn(
            'block text-xs font-medium',
            active && (tone === 'good' ? 'text-good' : 'text-bad'),
          )}
        >
          {title}
        </span>
        <span className="mt-0.5 block text-2xs leading-relaxed text-muted">{hint}</span>
      </span>
    </button>
  )
}
