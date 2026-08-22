/**
 * Bitta mijoz — kartochka va u bilan bo'lgan suhbatlar.
 *
 * SUKUT BO'YICHA BUTUN TARIX. Kartochkaga kirishdan maqsad — «bu
 * mijoz bilan umuman nima bo'lgan?» degan savol, shuning uchun
 * boshlanishida hech narsa kesilmaydi.
 *
 * DAVR TANLASH ham bor: «qachon va kim bilan gaplashgan?» degan
 * savolga javob shu. Tanlangan davr SAHIFANING HAMMASIGA tegadi —
 * ko'rsatkichlar, «kim gaplashgan» va suhbatlar jadvali. Faqat
 * jadvalni filtrlash chalkash bo'lardi: yuqoridagi 23 ta va
 * pastdagi 4 ta qator bir-biriga zid ko'rinardi.
 *
 * ⚠️ Bo'sh davr «mijoz topilmadi» EMAS: backend nollar bilan javob
 * qaytaradi va sahifa ochiq qoladi (`ClientRow.first_call_at`).
 *
 * ARALASH VAQT CHIZIG'I (savdo nazorati, 3-bosqich). Jadvalda
 * qo'ng'iroq va SAVDO bitta ro'yxatda turadi: rahbarning savoli
 * «ketma-ketlik saqlanganmi?» — qo'ng'iroq → savdo → qo'ng'iroq →
 * savdo. Ikki alohida jadval bu savolga javob bermasdi, sanalarni
 * ko'z bilan solishtirishga to'g'ri kelardi.
 *
 * ⚠️ SAVDO QATORLARI FAQAT `sales:read` BOR ODAMGA. Kartochkani savdo
 * xodimi ham ochadi (o'z mijozi), lekin savdo nazorati u ustidan olib
 * boriladigan tekshiruv — u yerda ko'rinmasligi kerak. Ruxsat bo'lmasa
 * so'rov umuman yuborilmaydi va sahifa AVVALGIDEK ishlaydi: bo'sh joy
 * ham, xato ham yo'q.
 */

import { ArrowLeft, Clock, PhoneMissed, ShoppingBag, Star, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

import { useAuth } from '@/modules/auth/store'
import { CallTypeBadge } from '@/modules/calls/CallTypeBadge'
import { DirectionMark } from '@/modules/calls/DirectionMark'
import {
  useClient,
  useClientCalls,
  useClientSales,
  type ClientCall,
  type ClientSale,
} from '@/modules/clients/api'
import { RuleBadges, VerdictBadge } from '@/modules/sales/badges'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { Page, PageHeader } from '@/shared/layout/Page'
import {
  formatFullDate,
  localDate,
  rangeToQuery,
  resolvePreset,
  useDateFormat,
  type DateRange,
} from '@/shared/lib/date'
import {
  cn,
  formatDuration,
  formatLongDuration,
  formatNumber,
  scoreTone,
  TONE_CLASS,
} from '@/shared/lib/utils'
import { Avatar, MiniBar } from '@/shared/ui/dataviz'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Segmented,
  Skeleton,
} from '@/shared/ui/primitives'

const PAGE_SIZE = 50

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * Savdoning vaqt chizig'idagi o'rni — o'sha KUNNING OXIRI.
 *
 * ⚠️ SAVDODA VAQT YO'Q, faqat sana (`docs/savdo-nazorati.md`, 2.1).
 * Ya'ni kun ichida savdo qaysi qo'ng'iroqdan oldin yoki keyin
 * bo'lganini BILIB BO'LMAYDI va biror taxmin tanlash shart.
 *
 * Tanlov qoidalar bilan bir xil: qoidalar savdo kunidagi suhbatni
 * savdodan OLDIN bo'lgan deb hisoblaydi (o'sha hujjat, 7.2/2).
 * Shuning uchun savdo o'sha kundagi qo'ng'iroqlardan KEYIN turadi —
 * yangisi tepada bo'lgan ro'yxatda bu ularning USTIDA degani. Aks
 * holda ekran «savdo → qo'ng'iroq» ko'rsatib, aynan o'zi tayangan
 * taxminga zid gapirardi. Izohda ham shu ochiq yoziladi.
 */
function saleAt(occurredOn: string): number {
  return localDate(occurredOn).getTime() + DAY_MS - 1
}

/** Aralash ro'yxatning bitta qatori — qo'ng'iroq yoki savdo. */
type TimelineRow =
  | { kind: 'call'; id: string; at: number; call: ClientCall }
  | { kind: 'sale'; id: string; at: number; sale: ClientSale }

export function ClientDetailPage() {
  const { t } = useTranslation()
  const { clientKey } = useParams<{ clientKey: string }>()
  const navigate = useNavigate()
  const fmt = useDateFormat()

  /* «Butun tarix» yoki tanlangan davr. Ikki holat ALOHIDA
     saqlanadi: «davr» rejimidan chiqib qaytgan odam o'zi tanlagan
     oraliqni qayta terib o'tirmasin. */
  const [mode, setMode] = useState<'all' | 'range'>('all')
  const [range, setRange] = useState<DateRange>(() => resolvePreset('last30'))

  const period = mode === 'range' ? rangeToQuery(range) : {}

  const [page, setPage] = useState(1)
  const detail = useClient(clientKey, period)
  const calls = useClientCalls(clientKey, {
    ...period,
    page,
    page_size: PAGE_SIZE,
  })

  /* ── Savdo tarixi ─────────────────────────────────────────
     Ruxsat bo'lmasa so'rov UMUMAN yuborilmaydi: 403 xatosi ham,
     bo'sh joy ham ko'rinmasin — sahifa avvalgidek ishlasin. */
  const canSeeSales = useAuth((state) => state.can)('sales:read')
  const sales = useClientSales(clientKey, period, { enabled: canSeeSales })

  const pages = Math.max(1, Math.ceil((calls.data?.total ?? 0) / PAGE_SIZE))

  /* ⚠️ SAHIFA CHEGARASIDAGI SAVDO QAYSI SAHIFAGA TUSHADI.

     Qo'ng'iroqlar sahifalab olinadi, savdolar esa hammasi birdan
     keladi — demak har savdo AYNAN BITTA sahifada ko'rinishi kerak:
     ikki sahifada takrorlansa son yolg'on bo'lardi, hech qaysisiga
     tushmasa esa qator JIMGINA yo'qolardi (eng yomoni).

     Sahifaning pastki chegarasi ma'lum (o'zidagi eng eski
     qo'ng'iroq), yuqorigisi esa OLDINGI sahifaning eng eski
     qo'ng'irog'i — u bu sahifada yo'q. Shuning uchun u bitta
     qo'ng'iroqlik alohida so'rov bilan olinadi: `page_size=1` da
     `page` global tartib raqamiga aylanadi, ya'ni `(page-1)*PAGE_SIZE`
     — aynan oldingi sahifaning oxirgi qatori. Natijada sahifalarning
     oynalari uzluksiz va kesishmaydigan bo'ladi. */
  const boundary = useClientCalls(
    clientKey,
    { ...period, page: (page - 1) * PAGE_SIZE, page_size: 1 },
    { enabled: canSeeSales && page > 1 },
  )
  const boundaryAt = boundary.data?.items[0]
    ? new Date(boundary.data.items[0].started_at).getTime()
    : null

  const timeline = useMemo<TimelineRow[]>(() => {
    const rows: TimelineRow[] = (calls.data?.items ?? []).map((call) => ({
      kind: 'call',
      id: `call-${call.id}`,
      at: new Date(call.started_at).getTime(),
      call,
    }))

    // Chegara hali kelmagan bo'lsa savdo QO'SHILMAYDI: taxmin qilib
    // qo'yilgan qator keyin joyini o'zgartirsa, ro'yxat sakrab
    // ko'rinardi.
    const saleRows = sales.data?.items ?? []
    const ready = page === 1 || boundaryAt !== null
    if (saleRows.length && ready) {
      const upper = page === 1 ? Infinity : (boundaryAt as number)
      const lower =
        page >= pages || !rows.length ? -Infinity : rows[rows.length - 1].at

      for (const sale of saleRows) {
        const at = saleAt(sale.occurred_on)
        // Yuqori chegara QAT'IY (`<`), pastkisi esa kiruvchi (`>=`):
        // shu tufayli qo'shni sahifalarning oynalari bir-biriga
        // tegib turadi, lekin ustma-ust tushmaydi.
        if (at < upper && at >= lower) {
          rows.push({ kind: 'sale', id: `sale-${sale.id}`, at, sale })
        }
      }
    }

    // Ikkilamchi mezon — bir xil vaqtli qatorlar har chizilganda
    // joyini almashtirmasligi uchun tartib BARQAROR bo'lsin.
    return rows.sort((a, b) => b.at - a.at || (a.id < b.id ? -1 : 1))
  }, [calls.data, sales.data, page, pages, boundaryAt])

  /* Savdosi umuman yo'q mijozda ekran AVVALGIDEK qoladi: yig'ma ham,
     yangi sarlavha ham paydo bo'lmaydi. */
  const showSales = canSeeSales && (sales.data?.total ?? 0) > 0

  if (detail.isLoading) {
    return (
      <Page>
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </Page>
    )
  }

  if (!detail.data) {
    return (
      <Page>
        <EmptyState
          message={t('clients.notFound')}
          action={{ label: t('common.back'), onClick: () => navigate('/clients') }}
        />
      </Page>
    )
  }

  const { client, agents } = detail.data

  return (
    <Page>
      <PageHeader
        /* Nomi bo'lmasa raqam sarlavha bo'ladi: «Noma'lum mijoz»
           degan yozuv hech narsa bermaydi, raqam esa taniladi */
        title={client.name || client.phone || client.key}
        /* Sarlavha ostidagi qator SONLAR QAYSI ORALIQQA tegishli
           ekanini aytadi. «Butun tarix» rejimida chegaralar ma'lumotdan
           olinadi (birinchi va oxirgi aloqa), davr tanlanganda esa
           tanlovning o'zidan — aks holda bo'sh davrda ko'rsatadigan
           sana qolmasdi. */
        subtitle={
          mode === 'all' && client.first_call_at && client.last_call_at
            ? t('clients.detail.period', {
                from: fmt.date(new Date(client.first_call_at)),
                to: fmt.date(new Date(client.last_call_at)),
                count: client.calls_total,
              })
            : t('clients.detail.periodRange', {
                from: fmt.date(range.from),
                to: fmt.date(range.to),
                count: client.calls_total,
              })
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Davr — «qachon va kim bilan gaplashgan?» degan savol
                uchun. Sukut «Butun tarix»: kartochka to'liq ochilsin,
                keyin foydalanuvchi o'zi toraytiradi. */}
            <Segmented
              value={mode}
              onChange={(value) => {
                setMode(value as 'all' | 'range')
                setPage(1)
              }}
              items={[
                { value: 'all', label: t('clients.detail.all') },
                { value: 'range', label: t('clients.detail.range') },
              ]}
            />
            {mode === 'range' && (
              <DateRangePicker
                value={range}
                onChange={(next) => {
                  setRange(next)
                  setPage(1)
                }}
              />
            )}
            <Button variant="secondary" onClick={() => navigate('/clients')}>
              <ArrowLeft className="size-4" />
              {t('common.back')}
            </Button>
          </div>
        }
      />

      {/* Raqam — sarlavhada nom turgan bo'lsa ham kerak: uni terib
          ko'rish yoki CRM da qidirish uchun ochiq turishi lozim */}
      {client.name && client.phone && (
        <p className="tnum text-sm text-muted">{client.phone}</p>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 2xl:gap-4">
        <Stat
          icon={Users}
          label={t('clients.colCalls')}
          value={formatNumber(client.calls_total)}
          sub={t('clients.inOut', {
            inbound: client.inbound,
            outbound: client.outbound,
          })}
        />
        <Stat
          icon={PhoneMissed}
          label={t('clients.colMissed')}
          value={formatNumber(client.missed)}
          sub={t('clients.missedHint')}
          tone={client.missed ? 'bad' : 'good'}
        />
        <Stat
          icon={Clock}
          label={t('clients.colTalk')}
          value={formatLongDuration(client.talk_seconds)}
          sub={t('clients.talkHint')}
        />
        <Stat
          icon={Star}
          label={t('clients.colScore')}
          value={client.avg_score != null ? String(Math.round(client.avg_score)) : '—'}
          /* Nechta suhbatdan hisoblangani AYTILADI: bitta baholangan
             suhbatdan chiqqan «92» bilan qirqtasidan chiqqani bir xil
             ko'rinmasligi kerak */
          sub={t('clients.scoredOf', {
            scored: client.scored,
            total: client.calls_total,
          })}
        />
      </div>

      {/* ── Kim gaplashgan ────────────────────────────────────
          Mijoz bir necha xodim bilan gaplashgan bo'lishi mumkin —
          almashinuv, ta'til, hududning o'zgarishi. Rahbarning
          birinchi savoli aynan shu bo'ladi. */}
      {/* Bo'sh davrda bu karta ko'rsatadigan narsa yo'q — o'rniga
          pastdagi jadval sababini aytadi */}
      {agents.length > 0 && (
      <Card>
        <CardHeader title={t('clients.agentsTitle')} hint={t('clients.agentsHint')} />
        <CardBody className="pt-0">
          <div className="flex flex-wrap gap-2">
            {agents.map((agent) => (
              <button
                key={agent.agent_id}
                onClick={() => navigate(`/agents/${agent.agent_id}`)}
                className="flex items-center gap-2.5 rounded-xl bg-surface-2/60 px-3 py-2 text-left transition-colors duration-250 ease-ios hover:bg-surface-2"
              >
                <Avatar
                  name={agent.full_name}
                  color={agent.color ?? undefined}
                  size="sm"
                />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{agent.full_name}</div>
                  <div className="text-2xs text-muted">
                    {agent.region ? `${agent.region} · ` : ''}
                    <span className="tnum">
                      {t('clients.agentCalls', { count: agent.calls })}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>
      )}

      {/* ── Vaqt chizig'i: qo'ng'iroq + savdo ─────────────── */}
      <Card>
        <CardHeader
          /* Sarlavha VAZIFANI aytadi. Savdo qatorlari ko'rinmasa
             jadval avvalgidek «Barcha suhbatlar» bo'lib qoladi —
             ruxsati yo'q odamga yo'q narsa va'da qilinmasin. */
          title={showSales ? t('clients.timeline.title') : t('clients.callsTitle')}
          hint={showSales ? t('clients.timeline.hint') : t('clients.callsHint')}
          action={
            calls.data ? (
              <span className="tnum text-xs text-muted">
                {formatNumber(calls.data.total)}
              </span>
            ) : undefined
          }
        />

        {/* Qisqa yig'ma — jadvaldan OLDIN. Rahbarning birinchi uch
            savoli: nechta savdo, qanchaga va nechtasi tekshirishni
            talab qiladi. Ular jadvalni varaqlamasdan javob olsin.

            ⚠️ Sonlar butun DAVR bo'yicha, ko'rilayotgan sahifa
            bo'yicha emas — aks holda «2 ta shubhali» degan son
            sahifadan sahifaga o'zgarib turardi. */}
        {showSales && sales.data && (
          <CardBody className="pt-0">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl bg-surface-2/50 px-3.5 py-2.5">
              <SaleStat
                label={t('clients.timeline.salesCount')}
                value={formatNumber(sales.data.total)}
              />
              <SaleStat
                label={t('clients.timeline.salesAmount')}
                value={`${formatNumber(Math.round(sales.data.amount_usd))} $`}
              />
              <SaleStat
                label={t('clients.timeline.salesSuspicious')}
                value={formatNumber(sales.data.suspicious)}
                tone={sales.data.suspicious > 0 ? 'warn' : 'muted'}
              />
              {/* «Tekshirib bo'lmadi» — YASHIRILMAYDI. U «toza»
                  degani emas, SAP dagi ma'lumot sifatining
                  ko'rsatkichi (shartnoma, 4-bo'lim). Noldan katta
                  bo'lsagina ko'rsatiladi: doimiy nol qator yig'mani
                  suyultirardi. */}
              {sales.data.not_checkable > 0 && (
                <SaleStat
                  label={t('clients.timeline.salesNotCheckable')}
                  value={formatNumber(sales.data.not_checkable)}
                />
              )}
              <span className="text-2xs leading-relaxed text-muted">
                {t('sales.windowNote', { count: sales.data.window_days })}
              </span>
            </div>
          </CardBody>
        )}

        {calls.isLoading ? (
          <CardBody className="space-y-2 pt-0">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </CardBody>
        ) : !timeline.length ? (
          /* Davr tanlangan bo'lsa bo'sh jadval «ma'lumot yo'q»
             degani EMAS — shu oraliqda aloqa bo'lmagan. Chiqish
             yo'li darhol taklif qilinadi. */
          <EmptyState
            message={t('table.empty')}
            hint={mode === 'range' ? t('clients.detail.emptyPeriod') : undefined}
            action={
              mode === 'range'
                ? {
                    label: t('clients.detail.all'),
                    onClick: () => {
                      setMode('all')
                      setPage(1)
                    },
                  }
                : undefined
            }
          />
        ) : (
          <div className="scroll-x">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <Th>{t('table.date')}</Th>
                  <Th>{t('clients.colDirection')}</Th>
                  <Th>{t('table.agent')}</Th>
                  <Th right>{t('table.duration')}</Th>
                  <Th right>{t('table.score')}</Th>
                  <Th right>{t('table.status')}</Th>
                </tr>
              </thead>
              <tbody>
                {timeline.map((row) => {
                  /* Savdo qatori ALOHIDA ko'rinadi: boshqa ikonka,
                     boshqa fon va summa. Aynan shu farq ketma-ketlikni
                     bir qarashda o'qishga imkon beradi — «qo'ng'iroq →
                     savdo → qo'ng'iroq → savdo» naqshi buzilgani ko'zga
                     tashlanadi. */
                  if (row.kind === 'sale') {
                    return (
                      <SaleRow
                        key={row.id}
                        sale={row.sale}
                        windowDays={sales.data?.window_days}
                      />
                    )
                  }

                  const call = row.call
                  const callTone = scoreTone(call.score) as
                    | 'accent'
                    | 'good'
                    | 'warn'
                    | 'bad'
                  const started = new Date(call.started_at)

                  return (
                    <tr
                      key={row.id}
                      onClick={() => navigate(`/calls/${call.id}`)}
                      className="cursor-pointer border-b border-border/60 transition-colors last:border-0 hover:bg-surface-2/60"
                    >
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="tnum text-sm">{fmt.date(started)}</div>
                        <div className="tnum text-2xs text-muted">
                          {fmt.time(started)}
                        </div>
                      </td>

                      {/* ⚠️ YO'NALISH SO'Z BILAN YOZILADI.
                          Belgining o'zi yetarli emas edi: «kiruvchi»
                          va «chiquvchi» butun tizimda XODIM tomonidan
                          o'qiladi, mijoz kartochkasida esa o'sha
                          so'zlar teskari tushunilardi («menga
                          kiruvchimi yoki mijozgami?»). Endi ikkala
                          tomon ham nomi bilan turadi. */}
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex items-center gap-2">
                          <DirectionMark
                            direction={call.direction}
                            answered={call.answered}
                          />
                          <div>
                            <div className="text-sm">
                              {call.direction === 'inbound'
                                ? t('clients.dirFromClient')
                                : t('clients.dirToClient')}
                            </div>
                            {/* Javob bo'lmagan bo'lsa — KIM ko'tarmagani.
                                Mijoz ko'tarmagani xodimning aybi emas,
                                shuning uchun u kulrang, kompaniya javob
                                bermagani esa qizil. */}
                            {call.answered === false && (
                              <div
                                className={cn(
                                  'text-2xs',
                                  call.direction === 'inbound'
                                    ? 'text-bad'
                                    : 'text-muted',
                                )}
                              >
                                {call.direction === 'inbound'
                                  ? t('clients.dirNoAnswer')
                                  : t('clients.dirNotPicked')}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar
                            name={call.agent_name}
                            color={call.agent_color ?? undefined}
                            size="sm"
                          />
                          <span className="truncate font-medium">
                            {call.agent_name}
                          </span>
                        </div>
                      </td>

                      <td className="tnum px-4 py-3 text-right text-muted">
                        {formatDuration(call.duration_sec)}
                      </td>

                      {/* Savdo bo'lmagan suhbat BAHOLANMAYDI — bo'sh
                          ball «AI ishlamadi» deb o'qilmasin */}
                      <td className="px-4 py-3">
                        {call.call_type && call.call_type !== 'sales' ? (
                          <div className="flex justify-end">
                            <CallTypeBadge type={call.call_type} compact />
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-2">
                            <span
                              className={cn('tnum font-semibold', TONE_CLASS[callTone])}
                            >
                              {call.score ?? '—'}
                            </span>
                            <MiniBar value={call.score} tone={callTone} width={44} />
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          {call.red_flag_count > 0 && (
                            <Badge tone="bad">
                              <span className="tnum">{call.red_flag_count}</span>
                            </Badge>
                          )}
                          {call.needs_review && (
                            <Badge tone="warn">{t('calls.review')}</Badge>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
            <span className="text-xs text-muted">
              {t('common.page')} <span className="tnum">{page}</span> {t('common.of')}{' '}
              <span className="tnum">{formatNumber(pages)}</span>
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t('common.prev')}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  )
}

/* ── Kichik qismlar ──────────────────────────────────────── */

/**
 * Vaqt chizig'idagi SAVDO qatori.
 *
 * ⚠️ OXIRGI UCH USTUN BITTA KATAKKA BIRLASHTIRILGAN (`colSpan`).
 * Sarlavhalar qo'ng'iroqniki — «Davomiylik», «Ball», «Holat» — va
 * savdoda ularning uchalasi ham yo'q. Summani «Davomiylik» ustuniga
 * yozib qo'yish jadvalni jimgina yolg'onga aylantirardi; birlashgan
 * katak esa savdo qatorining BOSHQA ekanini o'zi ko'rsatadi va
 * o'nga tortilgan summa baribir raqamlar ustunida turadi.
 *
 * Qator BOSILMAYDI: savdoning alohida sahifasi yo'q. Yolg'on
 * «bosiladigan» ko'rinish (kursor, hover) bo'sh va'da bo'lardi.
 */
function SaleRow({ sale, windowDays }: { sale: ClientSale; windowDays?: number }) {
  const { t } = useTranslation()

  return (
    <tr className="border-b border-border/60 bg-accent-soft/40 last:border-0">
      <td className="whitespace-nowrap px-4 py-3">
        <div className="tnum text-sm font-medium">
          {formatFullDate(`${sale.occurred_on}T00:00:00`)}
        </div>
        {/* Vaqt o'rnida — SAP dagi operatsiya raqami. Qo'ng'iroqda bu
            joyda soat turadi, savdoda esa soat YO'Q; raqam bo'sh
            joyni to'ldiribgina qolmay, rahbarga qatorni SAP da topish
            imkonini beradi. */}
        <div className="tnum text-2xs text-muted">{sale.external_id}</div>
      </td>

      <td className="whitespace-nowrap px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="icon-tile size-7 shrink-0 bg-accent-soft text-accent">
            <ShoppingBag className="size-3.5" />
          </span>
          <div>
            <div className="text-sm font-medium">{t('clients.timeline.sale')}</div>
            <div className="text-2xs text-muted">
              {t('clients.timeline.noTime')}
            </div>
          </div>
        </div>
      </td>

      <td className="px-4 py-3">
        <div className="max-w-[220px] truncate">
          {/* Xodimsiz savdo YASHIRILMAYDI: filiali biriktirilmagan
              qatorlar ham nazoratda turadi (shartnoma, 4-bo'lim) */}
          <span className={sale.agent_name ? '' : 'text-warn'}>
            {sale.agent_name ?? t('sales.noAgent')}
          </span>
        </div>
        <div className="truncate text-2xs text-muted">
          {sale.branch ?? '—'}
          {sale.direction ? ` · ${sale.direction}` : ''}
        </div>
      </td>

      <td className="px-4 py-3" colSpan={3}>
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1.5">
          {/* ⚠️ DALIL — XULOSA BILAN BIR QATORDA.

              Xulosani ko'rsatib, uni tekshirish imkonini bermaslik
              mumkin emas (shartnoma, 4-bo'lim: «har qator
              tekshiriladigan bo'lsin»). Vaqt chizig'i ketma-ketlikni
              ko'rsatadi, lekin «oxirgi suhbat necha kun oldin
              bo'lgan» degan songa ko'z bilan javob berib bo'lmaydi —
              ayniqsa suhbat sahifaning boshqa yeriga tushib qolsa.
              Shuning uchun son qatorning O'ZIDA turadi va nazorat
              ro'yxatidagi bilan bir xil so'z bilan yoziladi. */}
          {sale.verdict !== 'not_checkable' && (
            <span className="text-2xs leading-relaxed text-muted">
              {sale.last_call_at ? (
                <>
                  {formatFullDate(sale.last_call_at)}
                  {' · '}
                  {t('sales.daysBefore', { count: sale.days_before ?? 0 })}
                </>
              ) : (
                /* «Umuman yo'q» bo'sh katak bilan almashtirilmaydi:
                   bo'sh katak «ma'lumot yuklanmadi» deb o'qilardi,
                   bu esa aynan teskari xulosa. */
                <span className="text-warn">{t('sales.noCallEver')}</span>
              )}
            </span>
          )}
          {/* R2 ning dalili — oldingi savdo va oraliqdagi suhbatlar.
              «R2» yorlig'ini bilgan odam ham darhol «oldingi savdo
              qachon edi?» deb so'raydi. */}
          {sale.broken_rules.includes('R2') && sale.previous_sale_on && (
            <span className="text-2xs leading-relaxed text-muted">
              {t('sales.betweenCalls', {
                date: formatFullDate(`${sale.previous_sale_on}T00:00:00`),
                count: sale.calls_between,
              })}
            </span>
          )}
          {sale.broken_rules.includes('R3') && (
            <span className="text-2xs leading-relaxed text-bad">
              {t('sales.callsTotal', { count: sale.calls_total })}
            </span>
          )}
          {/* Buzilgan qoida BO'LSAGINA. `RuleBadges` bo'sh ro'yxatga
              «—» chizadi va u toza savdo yonida ortiqcha shovqin
              bo'lardi — bu yerda ustun emas, qator ichidagi belgi. */}
          {sale.broken_rules.length > 0 && (
            <RuleBadges rules={sale.broken_rules} windowDays={windowDays} />
          )}
          <VerdictBadge verdict={sale.verdict} skipReason={sale.skip_reason} />
          {/* Rahbar qaror qo'ygan bo'lsa u ham ko'rinadi: kartochkaga
              kirgan odam «bu allaqachon ko'rilganmi?» degan savolga
              javobni shu yerdan olsin */}
          {sale.review_status && (
            <Badge tone={sale.review_status === 'justified' ? 'good' : 'bad'}>
              {t(`sales.review.${sale.review_status}`)}
            </Badge>
          )}
          <div className="whitespace-nowrap text-right">
            {/* Dollar — asosiy son (valyutalar aralash bo'lgani uchun
                taqqoslash faqat unda ma'noli), hujjat valyutasi ostida */}
            <div className="tnum font-semibold">
              {sale.amount_usd != null
                ? `${formatNumber(Math.round(sale.amount_usd))} $`
                : '—'}
            </div>
            {sale.currency !== 'USD' && sale.amount != null && (
              <div className="tnum text-2xs text-muted">
                {formatNumber(Math.round(sale.amount))} {sale.currency}
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  )
}

/** Yig'madagi bitta son — yorlig'i bilan, bitta qatorda. */
function SaleStat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'warn' | 'muted'
}) {
  return (
    <span className="flex items-baseline gap-1.5 text-2xs">
      <span className={cn('tnum text-sm font-semibold', tone === 'warn' && 'text-warn')}>
        {value}
      </span>
      <span className="text-muted">{label}</span>
    </span>
  )
}

function Stat({
  icon: Icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: typeof Clock
  label: string
  value: string
  sub?: string
  tone?: 'good' | 'bad'
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
          <div className="tnum mt-0.5 text-2xl font-semibold leading-tight">{value}</div>
          {sub && <div className="mt-0.5 text-2xs text-muted">{sub}</div>}
        </div>
      </div>
    </Card>
  )
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={cn(
        'px-4 py-3 text-2xs font-medium uppercase tracking-wider text-muted',
        right && 'text-right',
      )}
    >
      {children}
    </th>
  )
}
