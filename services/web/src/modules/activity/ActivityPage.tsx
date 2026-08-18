/**
 * Qo'ng'iroq faolligi sahifasi.
 *
 * Uch qatlam: davr tanlash → kompaniya ko'rsatkichlari → xodimlar
 * jadvali. Tartib ataylab shunday: rahbar avval umumiy holatni
 * ko'radi, keyin kim sababchi ekanini topadi.
 *
 * ⚠️ ATAMALAR AJRATILGAN. «Javobsiz» degan yagona ustun YO'Q:
 *
 *   · «Javobsiz» ustuni  = KIRUVCHI javobsiz («propushenniy»).
 *     Mijoz qo'ng'iroq qildi, kompaniya javob bermadi.
 *   · «Ko'tarilmagan»    = CHIQUVCHI javobsiz. Mijoz ko'tarmadi.
 *
 * Ularni bir ustunga qo'shish raqamni ikki barobar oshirib, xodimni
 * nohaq ayblardi (o'lchandi: 7 kunda 983 va 1047).
 */

import { ArrowDownLeft, ArrowUpRight, PhoneMissed, UserX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  PERIODS,
  useActivity,
  type ActivityQuery,
  type ActivityRow,
  type Period,
} from '@/modules/activity/api'
import { CallsChart } from '@/modules/activity/CallsChart'
import { MissedClientsModal } from '@/modules/activity/MissedClientsModal'
import type { AnalyticsQuery } from '@/modules/analytics/api'
import { useAuth } from '@/modules/auth/store'
import { FilterBar } from '@/modules/dashboard/components/FilterBar'
import { Page, PageHeader } from '@/shared/layout/Page'
import { customRange, type DateRange } from '@/shared/lib/date'
import { cn, formatDuration, formatNumber } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Card, CardBody, CardHeader, EmptyState, Segmented, Skeleton } from '@/shared/ui/primitives'

/** Jadval ustunlari — nom va izoh BIR JOYDA.
 *
 *  Ikki alohida ro'yxat qilinsa ular vaqt o'tib bir-biridan ajralib
 *  ketardi: ustun qo'shilib, izohi unutilardi va hech narsa buni
 *  ko'rsatmasdi. */
const COLUMNS = [
  { key: 'out', label: 'activity.colOut', tip: 'activity.tipOut' },
  { key: 'outNo', label: 'activity.colOutNoAnswer', tip: 'activity.tipOutNoAnswer' },
  { key: 'in', label: 'activity.colIn', tip: 'activity.tipIn' },
  { key: 'missed', label: 'activity.colMissed', tip: 'activity.tipMissed' },
  { key: 'clients', label: 'activity.colClients', tip: 'activity.tipClients' },
  { key: 'unreached', label: 'activity.colUnreached', tip: 'activity.tipUnreached' },
  { key: 'rate', label: 'activity.colRate', tip: 'activity.tipRate' },
  { key: 'talk', label: 'activity.colTalk', tip: 'activity.tipTalk' },
] as const

/** «Oxirgi N kun» oralig'i — tez tugmachalar uchun.
 *
 *  `resolvePreset` ISHLATILMAYDI: undagi tayyor davrlar 7/30/45/90 va
 *  bu yerda kerak bo'lgan 1 va 15 kun yo'q. Ularni preset ro'yxatiga
 *  qo'shish esa butun tizimdagi sana tanlagichni o'zgartirardi —
 *  holbuki 1 va 15 kun faqat shu bo'limga tegishli. */
function lastDays(days: number): DateRange {
  const to = new Date()
  const from = new Date(to)
  from.setDate(from.getDate() - (days - 1))
  from.setHours(0, 0, 0, 0)
  return customRange(from, to)
}

/** Qaytish darajasining rangi.
 *
 *  Chegaralar HAQIQIY ma'lumotdan olingan: kompaniya o'rtachasi ~75%,
 *  eng yaxshi xodimlar 90%+, eng pasti 43%. Ya'ni 90 va 60 — «yaxshi»
 *  va «e'tibor kerak» ning haqiqiy chizig'i, o'ylab topilgan raqam
 *  emas. Foiz yo'q bo'lsa rang ham yo'q: javobsiz qo'ng'iroq
 *  bo'lmagan xodimni yashil ham, qizil ham qilib bo'lmaydi. */
function callbackTone(rate: number | null): string {
  if (rate === null) return 'text-muted'
  if (rate >= 90) return 'text-good'
  if (rate >= 60) return 'text-warn'
  return 'text-bad'
}

export function ActivityPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isSales = user?.role === 'sales'

  /* Tez tanlov: 1 kun / 1 hafta / 15 kun / 1 oy. Rahbar eng ko'p shu
     to'rttasini so'raydi, shuning uchun ular bitta bosishda. */
  const [days, setDays] = useState<Period>(7)

  /* To'liq filtr — sana oralig'i, xodim, hudud. `FilterBar` butun
     tizimda bir xil ishlaydi, shuning uchun qayta yozilmaydi.
     ⚠️ `score_min`/`has_red_flags` kabi BAHOGA tegishli maydonlar
     bu yerda ishlatilmaydi: bu bo'lim faqat qo'ng'iroq statistikasi
     uchun va sifat ko'rsatkichlari unga aralashmasligi kerak. */
  const [filters, setFilters] = useState<AnalyticsQuery>({})
  const [range, setRange] = useState<DateRange>(() => lastDays(7))

  /* Aniq oraliq tanlangan bo'lsa u ustun — backend ham shunday
     qaraydi. Tez tugmachalar esa `days` ni qo'yib, oraliqni tozalaydi. */
  const query = useMemo<ActivityQuery>(
    () => ({
      days,
      date_from: filters.date_from,
      date_to: filters.date_to,
      agent_ids: filters.agent_ids,
      regions: filters.regions,
    }),
    [days, filters],
  )

  const activity = useActivity(query)
  const total = activity.data?.total

  /* Kesim DAVRGA qarab tanlanadi: bir kunlik davrda kunlik grafik
     bitta nuqta bo'lib qolardi — mutlaqo foydasiz. Qaror serverdan
     kelgan `days` bo'yicha, mahalliy holat bo'yicha emas: aniq sana
     oralig'i tanlanganda ular farq qilishi mumkin. */
  const byHour = (activity.data?.days ?? days) <= 1

  /* Tanlangan xodim — tafsilot oynasi uchun. Jadvaldagi son ishonchsiz
     ko'rinsa («15 javobsiz, lekin 100% qaytish») bosib tekshirish
     mumkin bo'lishi kerak. */
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(null)

  /* Sichqoncha qaysi ustun ustida turibdi.
     ⚠️ Brauzerning o'z maslahatnomasi (`title`) ISHLAMAYDI: jadval
     `overflow-x: auto` konteyner ichida va u ikkala o'qni ham qirqadi,
     ya'ni maslahatnoma ko'rinmay qoladi. Shuning uchun izoh jadvaldan
     TASHQARIDA, doimiy joyda chiqadi. */
  const [hovered, setHovered] = useState<string | null>(null)

  return (
    <Page>
      <PageHeader
        title={t('activity.title')}
        /* Qamrov ochiq aytiladi. MoyZvonki'da qo'ng'iroqlar KO'PROQ:
           u yerdagi ba'zi hisoblar (HR, boshqa kompaniya) bizning
           xodimlar ro'yxatiga bog'lanmagan va hisobotga kirmaydi —
           o'lchandi, 3 kunda 100 qo'ng'iroq (~4%). Sonni aytmasak,
           «MoyZvonki boshqa raqam ko'rsatadi» degan savolga javob
           bo'lmasdi. */
        subtitle={
          activity.data
            ? t('activity.scope', {
                count: activity.data.agents.length,
                defaultValue: t('activity.subtitle'),
              })
            : t('activity.subtitle')
        }
        actions={
          <Segmented
            value={String(days)}
            onChange={(value) => {
              const next = Number(value) as Period
              setDays(next)
              /* Aniq oraliq backendda USTUN turadi — tozalanmasa tez
                 tugmacha bosilgani bilan hech narsa o'zgarmasdi va
                 foydalanuvchi buni nosozlik deb o'qirdi.
                 Sana tanlagichi ham shu oraliqqa keltiriladi, aks holda
                 unda boshqa davr yozilib turardi — ikki joyda ikki xil
                 javob eng yomon holat. */
              setFilters((f) => ({ ...f, date_from: undefined, date_to: undefined }))
              setRange(lastDays(next))
            }}
            items={PERIODS.map((p) => ({
              value: String(p),
              label: t(`activity.period.d${p}`),
            }))}
          />
        }
      />

      <FilterBar
        value={filters}
        onChange={(next) => {
          setFilters(next)
          /* Sana oralig'i tanlansa tez tugmacha o'z ma'nosini
             yo'qotadi — backend oraliqni ustun deb qaraydi */
        }}
        range={range}
        onRangeChange={setRange}
        showAgentFilter={!isSales}
        showRegionFilter={!isSales}
      />

      {/* ── Kompaniya ko'rsatkichlari ──────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 2xl:gap-4">
        <MetricCard
          icon={ArrowUpRight}
          label={t('activity.outbound')}
          hint={t('activity.outboundHint')}
          value={total?.outbound_total}
          sub={
            total
              ? t('activity.answeredOf', {
                  count: total.outbound_answered,
                  total: total.outbound_total,
                })
              : undefined
          }
          loading={activity.isLoading}
        />
        <MetricCard
          icon={ArrowDownLeft}
          label={t('activity.inbound')}
          hint={t('activity.inboundHint')}
          value={total?.inbound_total}
          sub={
            total
              ? t('activity.answeredOf', {
                  count: total.inbound_answered,
                  // Bilingan qatorlar — aks holda «952 ta javob berilgan
                  // (8498 tadan)» degan yozuv chiqib, holat haqiqiydan
                  // ancha yomon ko'rinardi
                  total: total.inbound_known,
                })
              : undefined
          }
          loading={activity.isLoading}
        />
        <MetricCard
          icon={PhoneMissed}
          label={t('activity.missed')}
          hint={t('activity.missedHint')}
          value={total?.missed}
          tone="bad"
          sub={
            total?.missed_rate != null
              ? t('activity.ofInbound', { percent: total.missed_rate })
              : undefined
          }
          loading={activity.isLoading}
        />
        {/* ⚠️ ASOSIY KARTA — MIJOZ darajasida.
            Hodisa soni («qancha qo'ng'iroq javobsiz qoldi») hajmni
            ko'rsatadi, bu esa HAQIQATNI: qancha ODAM bizga
            bog'lanolmadi va shundan qanchasi bilan keyin ham
            gaplashilmadi. Yo'qolgan savdo odamlar bilan o'lchanadi. */}
        <MetricCard
          icon={UserX}
          label={t('activity.unreached')}
          hint={t('activity.unreachedHint', {
            hours: activity.data?.callback_window_hours ?? 24,
          })}
          value={total?.clients_unreached}
          tone={total && total.clients_unreached > 0 ? 'bad' : 'good'}
          sub={
            total?.callback_rate != null
              ? t('activity.unreachedSub', {
                  reached: total.clients_reached,
                  clients: total.missed_clients,
                  percent: total.callback_rate,
                })
              : undefined
          }
          loading={activity.isLoading}
        />
      </div>

      {/* Median — kichik, lekin prezentatsiyada eng ko'p so'raladigan
          raqam: «qancha vaqtda qaytishadi?» */}
      {activity.data?.callback_median_minutes != null && (
        <p className="rounded-xl bg-surface-2/50 px-3.5 py-2.5 text-2xs leading-relaxed text-muted">
          {t('activity.medianNote', {
            minutes: activity.data.callback_median_minutes,
            hours: activity.data.callback_window_hours,
          })}
        </p>
      )}

      {/* Noma'lum qatorlar bor bo'lsa — JIM qolmaslik kerak, aks holda
          raqamlar nega kichik ekani tushunarsiz bo'ladi */}
      {total && total.unknown > 0 && (
        <p className="rounded-xl bg-warn/10 px-3.5 py-2.5 text-2xs leading-relaxed">
          {t('activity.unknownNote', { count: total.unknown })}
        </p>
      )}

      {/* ── Dinamika: kesim davrga MOSLASHADI ─────────────── */}
      <Card>
        <CardHeader
          title={byHour ? t('activity.chartTitleHour') : t('activity.chartTitle')}
          hint={t('activity.chartHint')}
        />
        <CardBody className="pt-2">
          {activity.isLoading ? (
            <Skeleton className="h-[280px] w-full" />
          ) : (
            <CallsChart
              days={activity.data?.days_series ?? []}
              hours={activity.data?.hours_series ?? []}
              byHour={byHour}
            />
          )}
        </CardBody>
      </Card>

      {/* ── Xodimlar jadvali ──────────────────────────────── */}
      <Card>
        <CardHeader
          title={isSales ? t('activity.myRow') : t('activity.byAgent')}
        />
        {/* Ustun izohi — jadvaldan TASHQARIDA, shuning uchun qirqilmaydi.
            Bo'sh bo'lganda umumiy tushuntirish turadi, ya'ni joy
            sakramaydi. */}
        <div className="px-5 pb-1">
          <p
            className={cn(
              'min-h-[2.6rem] text-2xs leading-relaxed transition-colors',
              hovered ? 'font-medium text-text' : 'text-muted',
            )}
          >
            {hovered
              ? t(COLUMNS.find((c) => c.key === hovered)?.tip ?? '')
              : t('activity.byAgentHint')}
          </p>
        </div>
        {activity.isLoading ? (
          <CardBody className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </CardBody>
        ) : !activity.data?.agents.length ? (
          <EmptyState message={t('table.empty')} />
        ) : (
          <div className="scroll-x">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <Th>{t('table.agent')}</Th>
                  {COLUMNS.map((column) => (
                    <Th
                      key={column.key}
                      right
                      active={hovered === column.key}
                      onHover={() => setHovered(column.key)}
                      onLeave={() => setHovered(null)}
                    >
                      {t(column.label)}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activity.data.agents.map((row) => (
                  <AgentRow
                    key={row.agent_id}
                    row={row}
                    onPick={
                      /* Javobsizi bo'lmagan xodimda ko'rsatadigan
                         narsa yo'q — tugma ham bo'lmaydi */
                      row.missed_clients
                        ? () =>
                            setPicked({ id: row.agent_id, name: row.agent_name })
                        : undefined
                    }
                  />
                ))}
              </tbody>
              {/* Jami qatori jadval ICHIDA — alohida kartada bo'lsa
                  ustunlar bilan taqqoslash uchun ko'z yugurtirish
                  kerak bo'lardi */}
              {activity.data.agents.length > 1 && total && (
                <tfoot>
                  <tr className="border-t-2 border-border font-semibold">
                    <Td>{t('activity.totalRow')}</Td>
                    <Td right>{formatNumber(total.outbound_total)}</Td>
                    <Td right>{formatNumber(total.outbound_no_answer)}</Td>
                    <Td right>{formatNumber(total.inbound_total)}</Td>
                    <Td right className="text-bad">
                      {formatNumber(total.missed)}
                    </Td>
                    <Td right>{formatNumber(total.missed_clients)}</Td>
                    <Td right className={total.clients_unreached ? 'text-bad' : undefined}>
                      {formatNumber(total.clients_unreached)}
                    </Td>
                    <Td right className={callbackTone(total.callback_rate)}>
                      {total.callback_rate != null ? `${total.callback_rate}%` : '—'}
                    </Td>
                    <Td right>{formatDuration(total.talk_seconds)}</Td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
      </Card>
      <MissedClientsModal
        agentId={picked?.id ?? null}
        agentName={picked?.name ?? ''}
        query={query}
        onClose={() => setPicked(null)}
      />
    </Page>
  )
}

/* ── Kichik qismlar ──────────────────────────────────────── */

function MetricCard({
  icon: Icon,
  label,
  hint,
  value,
  sub,
  tone,
  loading,
}: {
  icon: typeof PhoneMissed
  label: string
  hint: string
  value?: number
  sub?: string
  tone?: 'good' | 'bad'
  loading?: boolean
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'icon-tile size-9 shrink-0',
            tone === 'bad' && 'bg-bad/10 text-bad',
            tone === 'good' && 'bg-good/10 text-good',
            !tone && 'bg-accent-soft text-accent',
          )}
        >
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-2xs font-medium text-muted">{label}</div>
          {loading ? (
            <Skeleton className="mt-1 h-7 w-16" />
          ) : (
            <div className="tnum text-2xl font-semibold leading-tight">
              {value != null ? formatNumber(value) : '—'}
            </div>
          )}
          {sub && <div className="mt-0.5 text-2xs text-muted">{sub}</div>}
        </div>
      </div>
      <p className="mt-2.5 text-2xs leading-relaxed text-muted/70">{hint}</p>
    </Card>
  )
}

function AgentRow({
  row,
  onPick,
}: {
  row: ActivityRow
  /** Berilmasa qator bosilmaydi — ko'rsatadigan tafsilot yo'q */
  onPick?: () => void
}) {
  return (
    <tr
      onClick={onPick}
      className={cn(
        'border-b border-border/50 last:border-0',
        onPick && 'cursor-pointer transition-colors hover:bg-surface-2/60',
      )}
      title={onPick ? undefined : ''}
    >
      <Td>
        <div className="flex items-center gap-2.5">
          <Avatar name={row.agent_name} size="sm" />
          <div className="min-w-0">
            <div className="truncate font-medium">{row.agent_name}</div>
            {row.region && (
              <div className="truncate text-2xs text-muted">{row.region}</div>
            )}
          </div>
        </div>
      </Td>
      <Td right>{formatNumber(row.outbound_total)}</Td>
      <Td right className="text-muted">
        {formatNumber(row.outbound_no_answer)}
      </Td>
      <Td right>{formatNumber(row.inbound_total)}</Td>
      <Td right className={row.missed ? 'text-bad' : 'text-muted'}>
        {formatNumber(row.missed)}
      </Td>
      <Td right className="text-muted">
        {formatNumber(row.missed_clients)}
      </Td>
      {/* Bog'lanolmagan mijozlar — rahbarning ish ro'yxati, shuning
          uchun nol bo'lmaganda ajralib turadi */}
      <Td
        right
        className={row.clients_unreached ? 'font-semibold text-bad' : 'text-muted'}
      >
        {formatNumber(row.clients_unreached)}
      </Td>
      <Td right className={cn('font-semibold', callbackTone(row.callback_rate))}>
        {row.callback_rate != null ? `${row.callback_rate}%` : '—'}
      </Td>
      <Td right className="text-muted">
        {formatDuration(row.talk_seconds)}
      </Td>
    </tr>
  )
}

function Th({
  children,
  right,
  active,
  onHover,
  onLeave,
}: {
  children: React.ReactNode
  right?: boolean
  /** Izohi hozir ko'rsatilayotgan ustun */
  active?: boolean
  onHover?: () => void
  onLeave?: () => void
}) {
  const explainable = Boolean(onHover)
  return (
    <th
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      /* Sensorli ekranda sichqoncha yo'q — bosish ham ishlaydi */
      onClick={onHover}
      className={cn(
        'whitespace-nowrap px-3 py-2.5 text-2xs font-medium uppercase tracking-wide',
        right && 'text-right',
        explainable && 'cursor-help transition-colors',
        active ? 'text-accent' : 'text-muted',
      )}
    >
      {/* Nuqtali chiziq — ustun izohlanishi mumkinligini KO'RSATADI.
          Belgisiz foydalanuvchi sichqonchani olib borishni o'ylamaydi. */}
      <span
        className={cn(
          explainable && 'underline decoration-dotted decoration-from-font underline-offset-4',
          active && 'decoration-solid',
        )}
      >
        {children}
      </span>
    </th>
  )
}

function Td({
  children,
  right,
  className,
}: {
  children: React.ReactNode
  right?: boolean
  className?: string
}) {
  return (
    <td
      className={cn(
        'whitespace-nowrap px-3 py-2.5',
        right && 'tnum text-right',
        className,
      )}
    >
      {children}
    </td>
  )
}
