/**
 * Bitta mijoz — kartochka va u bilan bo'lgan BARCHA suhbatlar.
 *
 * ⚠️ DAVR FILTRI ATAYLAB YO'Q. Ro'yxatda davr tanlanadi (masalan «shu
 * oy»), bu yerda esa butun tarix ko'rinadi: kartochkaga kirishdan
 * maqsad — «bu mijoz bilan umuman nima bo'lgan?» degan savol.
 * Shuning uchun sarlavhada birinchi va oxirgi aloqa sanasi ochiq
 * yozilgan, ya'ni sonlar qaysi oraliqqa tegishli ekani ko'rinib
 * turadi va ro'yxatdagi son bilan farqi savol tug'dirmaydi.
 */

import { ArrowLeft, Clock, PhoneMissed, Star, Users } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

import { CallTypeBadge } from '@/modules/calls/CallTypeBadge'
import { DirectionMark } from '@/modules/calls/DirectionMark'
import { useClient, useClientCalls } from '@/modules/clients/api'
import { Page, PageHeader } from '@/shared/layout/Page'
import { useDateFormat } from '@/shared/lib/date'
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
  Skeleton,
} from '@/shared/ui/primitives'

const PAGE_SIZE = 50

export function ClientDetailPage() {
  const { t } = useTranslation()
  const { clientKey } = useParams<{ clientKey: string }>()
  const navigate = useNavigate()
  const fmt = useDateFormat()

  const [page, setPage] = useState(1)
  const detail = useClient(clientKey)
  const calls = useClientCalls(clientKey, { page, page_size: PAGE_SIZE })

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
  const pages = Math.max(1, Math.ceil((calls.data?.total ?? 0) / PAGE_SIZE))

  return (
    <Page>
      <PageHeader
        /* Nomi bo'lmasa raqam sarlavha bo'ladi: «Noma'lum mijoz»
           degan yozuv hech narsa bermaydi, raqam esa taniladi */
        title={client.name || client.phone || client.key}
        subtitle={t('clients.detail.period', {
          from: fmt.date(new Date(client.first_call_at)),
          to: fmt.date(new Date(client.last_call_at)),
          count: client.calls_total,
        })}
        actions={
          <Button variant="secondary" onClick={() => navigate('/clients')}>
            <ArrowLeft className="size-4" />
            {t('common.back')}
          </Button>
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

      {/* ── Suhbatlar ─────────────────────────────────────── */}
      <Card>
        <CardHeader
          title={t('clients.callsTitle')}
          hint={t('clients.callsHint')}
          action={
            calls.data ? (
              <span className="tnum text-xs text-muted">
                {formatNumber(calls.data.total)}
              </span>
            ) : undefined
          }
        />

        {calls.isLoading ? (
          <CardBody className="space-y-2 pt-0">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </CardBody>
        ) : !calls.data?.items.length ? (
          <EmptyState message={t('table.empty')} />
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
                {calls.data.items.map((call) => {
                  const callTone = scoreTone(call.score) as
                    | 'accent'
                    | 'good'
                    | 'warn'
                    | 'bad'
                  const started = new Date(call.started_at)

                  return (
                    <tr
                      key={call.id}
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
