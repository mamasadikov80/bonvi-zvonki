/**
 * Xronologiya — «qaysi savdolar orasida suhbat yo'q» degan savolga
 * BIR QARASHDA javob.
 *
 * ⚠️ NEGA KERAK. Nazorat ro'yxati sonlarni beradi («orasida 0 ta
 * suhbat»), lekin son ketma-ketlikni ko'rsatmaydi. Rahbar — ayniqsa
 * direktor — jadval o'qib emas, KO'Z bilan qaror qiladi: suhbat va
 * savdo bitta chiziqda tursa, «savdo → savdo → savdo, orada hech
 * narsa yo'q» naqshi o'zi ko'rinadi.
 *
 * ⚠️ YANGI SO'ROV YO'Q. Ikkala manba ham tayyor: mijozning savdolari
 * (`/clients/{key}/sales`) va suhbatlari (`/clients/{key}/calls`).
 * Ular sana bo'yicha aralashtiriladi — nazorat ro'yxati bilan bir
 * xil manbadan (`ComplianceService`) kelgani uchun sonlar ham
 * ziddiyatsiz bo'ladi.
 *
 * ⚠️ SAVDODA VAQT YO'Q, faqat sana. Bir kunda ikkalasi bo'lsa
 * qo'ng'iroq OLDIN ko'rsatiladi — qoidalar ham aynan shunday
 * hisoblaydi (savdo kunidagi suhbat savdodan oldin bo'lgan deb
 * qaraladi). Bu taxmin oynada ochiq yoziladi, aks holda ekran o'zi
 * tayangan taxminga zid gapirardi.
 *
 * ⚠️ ±30 KUN. Butun tarix shovqin bo'lardi: savdo atrofidagi bir oy
 * — qoidalarning oynasidan (odatda 3 kun) ancha keng va «oldingi
 * savdo» ham deyarli har doim shu oraliqqa tushadi.
 */

import { CalendarClock, ShoppingBag, TriangleAlert } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/modules/auth/store'
import { DirectionMark } from '@/modules/calls/DirectionMark'
import {
  useClientCalls,
  useClientSales,
  type ClientCall,
  type ClientSale,
} from '@/modules/clients/api'
import type { ComplianceRow } from '@/modules/sales/api'
import { SkipBadge, VerdictBadge } from '@/modules/sales/badges'
import { useSaleReason } from '@/modules/sales/reason'
import { formatFullDate, formatTime, localDate } from '@/shared/lib/date'
import { cn, formatLongDuration, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, EmptyState, Skeleton } from '@/shared/ui/primitives'

/** Savdo atrofidagi oyna — har tomonga. */
const AROUND_DAYS = 30

const DAY_MS = 24 * 60 * 60 * 1000

/** Ro'yxatda ko'rsatiladigan suhbatlar chegarasi (backendda `le=200`) */
const CALLS_LIMIT = 100

/**
 * Savdoning chiziqdagi o'rni — KUN OXIRI.
 *
 * Shu tufayli o'sha kundagi qo'ng'iroqlar savdodan OLDIN turadi, ya'ni
 * ekran qoidalar bilan bir xil taxminda bo'ladi (`ClientDetailPage`
 * dagi bilan aynan bir xil qoida).
 */
function saleAt(occurredOn: string): number {
  return localDate(occurredOn).getTime() + DAY_MS - 1
}

type Row =
  | { kind: 'call'; id: string; at: number; call: ClientCall }
  | { kind: 'sale'; id: string; at: number; sale: ClientSale }

export function SaleTimelineModal({
  sale,
  windowDays,
  onClose,
  onReview,
}: {
  /** `null` — oyna yopiq */
  sale: ComplianceRow | null
  windowDays?: number
  onClose: () => void
  /** Qaror qo'yish — ruxsati borlarda. Berilmasa tugma ham yo'q. */
  onReview?: (sale: ComplianceRow) => void
}) {
  const { t } = useTranslation()
  const can = useAuth((state) => state.can)
  const reasonOf = useSaleReason(windowDays)

  /* Suhbatlar `calls:read` talab qiladi, savdolar esa `sales:read`.
     Ruxsat bo'lmasa so'rov UMUMAN yuborilmaydi: 403 xatosi o'rniga
     oyna faqat savdolarni ko'rsatadi. */
  const canReadCalls = can('calls:read') || can('calls:read:own')

  const key = sale?.phone_key ?? undefined
  const occurredOn = sale?.occurred_on

  const period = useMemo(() => {
    if (!occurredOn) return {}
    const from = localDate(occurredOn)
    from.setDate(from.getDate() - AROUND_DAYS)
    const to = localDate(occurredOn)
    to.setDate(to.getDate() + AROUND_DAYS)
    to.setHours(23, 59, 59, 999)
    return { date_from: from.toISOString(), date_to: to.toISOString() }
  }, [occurredOn])

  const calls = useClientCalls(
    key,
    { ...period, page: 1, page_size: CALLS_LIMIT },
    { enabled: canReadCalls },
  )
  const sales = useClientSales(key, period)

  const rows = useMemo<Row[]>(() => {
    const list: Row[] = []

    for (const call of calls.data?.items ?? []) {
      list.push({
        kind: 'call',
        id: `call-${call.id}`,
        at: new Date(call.started_at).getTime(),
        call,
      })
    }

    const saleRows = sales.data?.items ?? []
    for (const row of saleRows) {
      list.push({
        kind: 'sale',
        id: `sale-${row.id}`,
        at: saleAt(row.occurred_on),
        sale: row,
      })
    }

    /* ⚠️ SHU SAVDONING O'ZI HAR DOIM RO'YXATDA BO'LADI. Odatda u
       `/clients/{key}/sales` javobida keladi, lekin so'rov
       bajarilmagan bo'lsa ham (ruxsat, tarmoq) oyna «savdo yo'q»
       deb ko'rsatmasligi kerak — bu aynan teskari xulosa. */
    if (sale && !saleRows.some((row) => row.id === sale.id)) {
      list.push({
        kind: 'sale',
        id: `sale-${sale.id}`,
        at: saleAt(sale.occurred_on),
        sale: selfSale(sale),
      })
    }

    // Eskisidan yangisiga — hikoya shu tartibda o'qiladi. Ikkilamchi
    // mezon tartibni BARQAROR qiladi: bir xil vaqtli qatorlar har
    // chizilganda joyini almashtirmasin.
    return list.sort((a, b) => a.at - b.at || (a.id < b.id ? -1 : 1))
  }, [calls.data, sales.data, sale])

  const loading = sales.isLoading || (canReadCalls && calls.isLoading)

  /* Chegaraga urilgan bo'lsa JIM QOLMAYDI: ko'rsatilmagan suhbat
     borligini aytmaslik — «suhbat yo'q» degan yolg'on xulosa. */
  const hiddenCalls = Math.max(
    0,
    (calls.data?.total ?? 0) - (calls.data?.items.length ?? 0),
  )

  return (
    <Modal
      open={sale !== null}
      onOpenChange={(open) => !open && onClose()}
      title={t('sales.timeline.title')}
      description={
        sale
          ? [sale.partner_name, sale.partner_code, sale.phone].filter(Boolean).join(' · ')
          : undefined
      }
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.close')}
          </Button>
          {sale && onReview && (
            <Button onClick={() => onReview(sale)}>{t('sales.timeline.decide')}</Button>
          )}
        </>
      }
    >
      {sale && (
        <div className="space-y-4">
          {/* Sarlavha ostidagi bitta qator: xulosa, qoidalar va oyna */}
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={sale.verdict} skipReason={sale.skip_reason} />
            {sale.skip_reason && <SkipBadge reason={sale.skip_reason} />}
            <span className="text-2xs text-muted">
              {t('sales.timeline.window', { count: AROUND_DAYS })}
            </span>
          </div>

          {!sale.phone_key ? (
            /* Telefonsiz mijozda xronologiya TUZIB BO'LMAYDI va bu
               nosozlik emas — aynan «tekshirib bo'lmadi» xulosasining
               sababi. Shuning uchun bo'sh ro'yxat emas, izoh. */
            <EmptyState
              message={t('sales.timeline.noPhone')}
              hint={
                sale.skip_reason ? t(`sales.skip.${sale.skip_reason}`) : undefined
              }
            />
          ) : loading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <>
              <ol className="space-y-1.5">
                {rows.map((row) =>
                  row.kind === 'call' ? (
                    <CallLine key={row.id} call={row.call} />
                  ) : (
                    <SaleLine
                      key={row.id}
                      sale={row.sale}
                      reason={reasonOf(row.sale)}
                      current={row.sale.id === sale.id}
                    />
                  ),
                )}
              </ol>

              {rows.length === 1 && (
                <p className="text-2xs leading-relaxed text-muted">
                  {t('sales.timeline.empty', { count: AROUND_DAYS })}
                </p>
              )}

              {hiddenCalls > 0 && (
                <p className="text-2xs leading-relaxed text-muted">
                  {t('sales.timeline.more', { count: hiddenCalls })}
                </p>
              )}
            </>
          )}

          {/* Taxmin OCHIQ aytiladi — ekran o'zi tayangan qoidani
              yashirsa, tartibga ishonib bo'lmasdi */}
          <p className="rounded-xl bg-surface-2/50 px-3.5 py-2.5 text-2xs leading-relaxed text-muted">
            {t('sales.timeline.noTime')}
          </p>
        </div>
      )}
    </Modal>
  )
}

/* ── Chiziqdagi qatorlar ─────────────────────────────────── */

function Line({
  at,
  mark,
  children,
  className,
}: {
  /** Chapdagi sana — hamma qatorda bir xil kenglikda turadi */
  at: string | Date
  mark: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <li
      className={cn(
        'flex items-start gap-3 rounded-xl px-3 py-2 ring-1 ring-inset ring-transparent',
        className,
      )}
    >
      <span className="tnum w-[5.5rem] shrink-0 pt-0.5 text-2xs text-muted">
        {formatFullDate(at)}
      </span>
      {mark}
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  )
}

function CallLine({ call }: { call: ClientCall }) {
  const { t } = useTranslation()
  const started = new Date(call.started_at)

  return (
    <Line
      at={started}
      mark={<DirectionMark direction={call.direction} answered={call.answered} />}
      className="bg-surface-2/40"
    >
      <div className="truncate text-sm">
        {t('sales.timeline.call')}
        <span className="text-muted"> · </span>
        <span className="text-muted">{call.agent_name}</span>
      </div>
      <div className="tnum truncate text-2xs text-muted">
        {formatTime(started)}
        {' · '}
        {call.direction === 'inbound'
          ? t('clients.dirFromClient')
          : t('clients.dirToClient')}
        {' · '}
        {/* Javobsiz suhbatning davomiyligi 0 va uni «0 son» deb
            yozish yolg'on bo'lardi — gap umuman bo'lmagan */}
        {call.answered === false
          ? call.direction === 'inbound'
            ? t('clients.dirNoAnswer')
            : t('clients.dirNotPicked')
          : formatLongDuration(call.duration_sec)}
      </div>
    </Line>
  )
}

function SaleLine({
  sale,
  reason,
  current,
}: {
  sale: ClientSale
  reason: string
  /** Ro'yxat aynan SHU savdo uchun ochilgan */
  current: boolean
}) {
  const { t } = useTranslation()
  /* R2 — «ikki savdo orasida suhbat yo'q». Aynan shu holat
     xronologiyaning butun ma'nosi, shuning uchun u kulrang izoh
     emas, ogohlantirish bo'lib turadi. */
  const gap = sale.broken_rules.includes('R2')

  return (
    <Line
      at={`${sale.occurred_on}T00:00:00`}
      mark={
        <span className="icon-tile size-6 shrink-0 bg-accent-soft text-accent">
          <ShoppingBag className="size-3.5" />
        </span>
      }
      className={cn(
        current ? 'bg-accent-soft/70 ring-accent/30' : 'bg-surface-2/70',
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium">
          {t('clients.timeline.sale')}
          <span className="text-muted"> · </span>
          <span className="tnum">
            {sale.amount_usd != null
              ? `${formatNumber(Math.round(sale.amount_usd))} $`
              : '—'}
          </span>
        </span>
        {current && (
          <Badge tone="accent" className="whitespace-nowrap">
            {t('sales.timeline.thisSale')}
          </Badge>
        )}
      </div>
      {reason && (
        <div
          className={cn(
            'mt-0.5 flex items-start gap-1.5 text-2xs',
            gap ? 'text-warn' : 'text-muted',
          )}
        >
          {gap ? (
            <TriangleAlert className="mt-0.5 size-3 shrink-0" />
          ) : (
            <CalendarClock className="mt-0.5 size-3 shrink-0 opacity-60" />
          )}
          <span>{reason}</span>
        </div>
      )}
    </Line>
  )
}

/* ── Nazorat qatoridan savdo qatori ──────────────────────── */

/**
 * `ComplianceRow` → `ClientSale`.
 *
 * Maydonlar ikkala javobda ham AYNAN bir xil nomlanadi (backend
 * shartnomasi, 7.1) — farq faqat qarorda: ro'yxatda to'liq obyekt,
 * kartochkada esa faqat holati.
 */
function selfSale(row: ComplianceRow): ClientSale {
  return {
    id: row.id,
    occurred_on: row.occurred_on,
    external_id: row.external_id,
    branch: row.branch,
    direction: row.direction,
    agent_id: row.agent_id,
    agent_name: row.agent_name,
    amount: row.amount,
    currency: row.currency,
    amount_usd: row.amount_usd,
    verdict: row.verdict,
    broken_rules: row.broken_rules,
    skip_reason: row.skip_reason,
    last_call_at: row.last_call_at,
    last_call_agent: row.last_call_agent,
    days_before: row.days_before,
    previous_sale_on: row.previous_sale_on,
    calls_between: row.calls_between,
    calls_total: row.calls_total,
    review_status: row.review?.status ?? null,
  }
}
