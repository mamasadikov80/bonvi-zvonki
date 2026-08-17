/**
 * Xodim bo'yicha tafsilot — RAQAMNI ISBOTLAYDI.
 *
 * NEGA KERAK. Jadvalda «15 javobsiz, 100% qaytish» degan qator g'alati
 * tuyuladi va birinchi savol shu bo'ladi: «rostdanmi?». Aslida to'g'ri —
 * 15 hodisa 9 xil mijozdan kelgan, ba'zilari 2-3 marta urinib ko'rgan va
 * hammasi bilan gaplashilgan. Lekin buni ko'rsatmasa raqamga ishonch
 * bo'lmaydi.
 *
 * Shuning uchun bu oyna har bir mijozni alohida ko'rsatadi: necha marta
 * urinib ko'rgan, oxirgi urinish qachon, keyin KIM bilan va QANCHA
 * vaqtdan so'ng gaplashgan. Urinishlar yig'indisi jadvaldagi «javobsiz»
 * soniga, qatorlar soni «mijoz» soniga teng bo'lishi kerak — oynaning
 * pastida shu tenglik ko'rsatiladi.
 *
 * Bog'lanmaganlar YUQORIDA turadi: ro'yxat ish uchun.
 */

import { CheckCircle2, PhoneIncoming, PhoneOutgoing, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useMissedClients, type ActivityQuery } from '@/modules/activity/api'
import { useDateFormat } from '@/shared/lib/date'
import { cn } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, EmptyState, Skeleton } from '@/shared/ui/primitives'

export function MissedClientsModal({
  agentId,
  agentName,
  query,
  onClose,
}: {
  agentId: string | null
  agentName: string
  query: ActivityQuery
  onClose: () => void
}) {
  const { t } = useTranslation()
  const fmt = useDateFormat()
  const report = useMissedClients(agentId, query)

  const rows = report.data?.clients ?? []
  const attempts = rows.reduce((sum, row) => sum + row.attempts, 0)

  return (
    <Modal
      open={Boolean(agentId)}
      onOpenChange={(open) => !open && onClose()}
      title={agentName}
      size="lg"
    >
      {report.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !rows.length ? (
        <EmptyState message={t('activity.noMissed')} />
      ) : (
        <>
          <p className="mb-3 text-2xs leading-relaxed text-muted">
            {t('activity.drillHint', {
              hours: report.data?.callback_window_hours ?? 24,
            })}
          </p>

          <div className="scroll-x">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <Th>{t('activity.drillClient')}</Th>
                  <Th right>{t('activity.drillAttempts')}</Th>
                  <Th>{t('activity.drillLastMissed')}</Th>
                  <Th>{t('activity.drillContact')}</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const reached = row.contacted_at !== null
                  return (
                    <tr
                      key={row.phone}
                      className="border-b border-border/50 last:border-0"
                    >
                      <Td>
                        <div className="flex items-center gap-2">
                          {reached ? (
                            <CheckCircle2 className="size-4 shrink-0 text-good" />
                          ) : (
                            <XCircle className="size-4 shrink-0 text-bad" />
                          )}
                          <div className="min-w-0">
                            <div className="tnum truncate font-medium">
                              {row.phone}
                            </div>
                            {row.client_name && (
                              <div className="truncate text-2xs text-muted">
                                {row.client_name}
                              </div>
                            )}
                          </div>
                        </div>
                      </Td>
                      <Td right className={row.attempts > 1 ? 'font-semibold' : undefined}>
                        {row.attempts}
                      </Td>
                      <Td className="tnum whitespace-nowrap text-muted">
                        {fmt.date(new Date(row.last_missed_at))}{' '}
                        {fmt.time(new Date(row.last_missed_at))}
                      </Td>
                      <Td>
                        {!reached ? (
                          <Badge tone="bad">{t('activity.drillNotReached')}</Badge>
                        ) : (
                          <div className="flex flex-wrap items-center gap-1.5">
                            {/* Yo'nalish belgisi: mijoz o'zi qayta
                                urindimi yoki xodim qaytardimi — ikkisi
                                boshqa ma'no beradi */}
                            {row.contact_inbound ? (
                              <PhoneIncoming className="size-3.5 shrink-0 text-accent" />
                            ) : (
                              <PhoneOutgoing className="size-3.5 shrink-0 text-good" />
                            )}
                            <span className="tnum text-2xs">
                              {t('activity.drillAfter', {
                                minutes: row.minutes_to_contact,
                              })}
                            </span>
                            {row.contacted_by && (
                              <span className="text-2xs text-muted">
                                · {row.contacted_by}
                              </span>
                            )}
                          </div>
                        )}
                      </Td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* ⚠️ TENGLIK KO'RSATILADI. Bu oyna raqamni isbotlash uchun,
              shuning uchun jadvaldagi sonlar bilan bog'liqligi ochiq
              aytiladi: qatorlar soni = «mijoz», urinishlar yig'indisi =
              «javobsiz». */}
          <p className="mt-3 rounded-xl bg-surface-2/60 px-3.5 py-2.5 text-2xs leading-relaxed text-muted">
            {t('activity.drillTotals', {
              clients: rows.length,
              attempts,
              unreached: report.data?.unreached ?? 0,
            })}
          </p>
        </>
      )}
    </Modal>
  )
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={cn(
        'whitespace-nowrap px-2.5 py-2 text-2xs font-medium uppercase tracking-wide text-muted',
        right && 'text-right',
      )}
    >
      {children}
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
    <td className={cn('px-2.5 py-2.5', right && 'tnum text-right', className)}>
      {children}
    </td>
  )
}
