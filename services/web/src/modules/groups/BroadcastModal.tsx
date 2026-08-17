/**
 * «Barcha guruhlarga so'rovnoma» — tasdiqlash va natija oynasi.
 *
 * Nega tasdiqlash majburiy: bu tugma haqiqiy mijozlar o'tirgan
 * yuzlab Telegram guruhlariga xabar yuboradi. Yuborilgan xabarni
 * qaytarib bo'lmaydi.
 *
 * MIQYOS TUZATISHI: ilgari bu oyna butun guruhlar ro'yxatini tortib
 * olib, har birini nomma-nom sanab chiqardi. ~1000 ta guruhda bu
 * na mumkin, na foydali — hech kim 1000 qatorli ro'yxatni o'qib
 * tasdiqlamaydi. Endi oyna DARAXT SANOQLARIDAN ishlaydi
 * (`GET /groups/tree` — bitta yengil so'rov) va uch raqamni
 * ko'rsatadi: nechtasi tayyor, nechtasida xodim yo'q, nechtasida
 * hudud yo'q. Kim tushib qolgani esa daraxtning o'zida ko'rinadi.
 */

import { AlertTriangle, CheckCircle2, Clock, Info, MapPin, Send, Users2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  BOT_POLL_SECONDS,
  errorMessage,
  sortRegionNodes,
  treeTotals,
  useBroadcastSurveys,
  useGroupsTree,
  type BroadcastResult,
} from '@/modules/groups/api'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Avatar } from '@/shared/ui/dataviz'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, Skeleton } from '@/shared/ui/primitives'

export function BroadcastModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()

  const tree = useGroupsTree(open)
  const broadcast = useBroadcastSurveys()

  const [result, setResult] = useState<BroadcastResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Oyna yopilib qayta ochilsa eski natija ko'rinmasin
  useEffect(() => {
    if (!open) return
    setResult(null)
    setError(null)
  }, [open])

  const totals = treeTotals(tree.data)
  const ready = Math.max(0, totals.groups - totals.unassigned - totals.regionless)
  const loading = tree.isLoading

  /* Xodimlar kesimi: kimga nechta xabar tushadi. Guruhlar emas,
     XODIMLAR sanaladi — ro'yxat 15 qator, 1000 emas. */
  const perAgent = (tree.data?.agents ?? [])
    .map((agent) => ({
      agent,
      ready: sortRegionNodes(agent.regions)
        .filter((node) => node.region !== null)
        .reduce((sum, node) => sum + node.group_count, 0),
    }))
    .filter((row) => row.ready > 0)
    .sort((a, b) => b.ready - a.ready)

  const run = () => {
    setError(null)
    broadcast.mutate(undefined, {
      onSuccess: setResult,
      onError: (e) => setError(errorMessage(e, t('common.error'))),
    })
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={result ? t('groups.broadcastDoneTitle') : t('groups.broadcastTitle')}
      description={
        result ? t('groups.broadcastDoneHint') : t('groups.broadcastIrreversible')
      }
      size="md"
      footer={
        result ? (
          <Button onClick={onClose}>{t('common.close')}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={broadcast.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={loading || broadcast.isPending || ready === 0}
              onClick={run}
            >
              <Send className="size-4" />
              {broadcast.isPending
                ? t('groups.broadcastSending')
                : t('groups.broadcastConfirm', { count: ready })}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <ResultView result={result} />
      ) : loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Asosiy raqam — admin shu bittasini o'qib qaror qiladi */}
          <div
            className={cn(
              'flex items-start gap-3 rounded-2xl p-4',
              ready ? 'bg-accent-soft' : 'bg-warn/[0.08]',
            )}
          >
            <span className={cn('icon-tile size-10 shrink-0', ready ? 'text-accent' : 'text-warn')}>
              {ready ? <Users2 className="size-5" /> : <AlertTriangle className="size-5" />}
            </span>
            <div className="min-w-0">
              {ready ? (
                <>
                  <p className="text-sm font-semibold text-text">
                    {t('groups.broadcastCount', { count: ready })}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    {t('groups.broadcastPerAgent')}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-warn">
                    {t('groups.broadcastNone')}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    {t('groups.broadcastNoneHint')}
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Tushmaydiganlar — sabab bo'yicha yig'ma, nomma-nom emas */}
          {(totals.unassigned > 0 || totals.regionless > 0) && (
            <div className="rounded-2xl bg-warn/[0.07] p-3.5">
              <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-warn">
                <AlertTriangle className="size-3.5" />
                {t('groups.broadcastWillSkip', {
                  count: totals.unassigned + totals.regionless,
                })}
              </div>
              <ul className="space-y-1.5 text-xs leading-relaxed">
                {totals.unassigned > 0 && (
                  <li className="flex items-center gap-2">
                    <span className="size-1.5 shrink-0 rounded-full bg-warn" />
                    <span>{t('groups.tree.unassignedTitle')}</span>
                    <span className="tnum ml-auto font-semibold">
                      {formatNumber(totals.unassigned)}
                    </span>
                  </li>
                )}
                {totals.regionless > 0 && (
                  <li className="flex items-center gap-2">
                    <span className="size-1.5 shrink-0 rounded-full bg-warn" />
                    <span>{t('groups.tree.regionless')}</span>
                    <span className="tnum ml-auto font-semibold">
                      {formatNumber(totals.regionless)}
                    </span>
                  </li>
                )}
              </ul>
              <p className="mt-2 text-2xs leading-relaxed text-muted">
                {t('groups.broadcastSkipWhere')}
              </p>
            </div>
          )}

          {/* Kimga tushadi — XODIMLAR kesimida, ro'yxat qisqa qoladi */}
          {perAgent.length > 0 && (
            <div className="rounded-2xl bg-surface-2/60 p-3.5">
              <div className="mb-2 text-2xs font-medium uppercase tracking-wider text-muted">
                {t('groups.broadcastRecipients')}
              </div>
              <ul className="max-h-44 space-y-1.5 overflow-y-auto">
                {perAgent.map(({ agent, ready: count }) => (
                  <li key={agent.agent_id} className="flex items-center gap-2 text-xs">
                    <Avatar
                      name={agent.full_name}
                      color={agent.color ?? undefined}
                      src={agent.avatar_url}
                      size="sm"
                    />
                    <span className="truncate font-medium">{agent.full_name}</span>
                    <span className="tnum ml-auto shrink-0 text-2xs text-muted">
                      {t('groups.groupCount', { count })}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Vaqt qoidalari ishlamasligi — tugmaning butun mazmuni shu */}
          <div className="space-y-2">
            <Note icon={Clock} tone="muted">
              {t('groups.broadcastForce')}
            </Note>
            <Note icon={AlertTriangle} tone="warn">
              {t('groups.broadcastRealPeople')}
            </Note>
            <Note icon={MapPin} tone="muted">
              {t('groups.broadcastEstimate')}
            </Note>
            <Note icon={Info} tone="muted">
              {t('groups.broadcastDelay', { seconds: BOT_POLL_SECONDS })}
            </Note>
          </div>

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

/* ── Natija ──────────────────────────────────────────────────
   Uch raqam ham aytiladi: yaratilgan, takrorlanmagani va
   o'tkazib yuborilgani. «8 ta yuborildi» degan yarim haqiqat
   adminni Guruhlar sahifasida sanashga majbur qilardi.

   O'tkazib yuborilganlar ro'yxati ham CHEKLANADI: 1000 ta guruhda
   u yuzlab qator bo'lishi mumkin. Birinchi 20 tasi ko'rsatiladi,
   qolgani sanoq bilan aytiladi. */

const SKIP_PREVIEW = 20

function ResultView({ result }: { result: BroadcastResult }) {
  const { t } = useTranslation()
  const shown = result.skipped.slice(0, SKIP_PREVIEW)
  const hidden = result.skipped.length - shown.length

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-2xl bg-good/10 p-4">
        <span className="icon-tile size-10 shrink-0 text-good">
          <CheckCircle2 className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-good">
            {t('groups.broadcastCreated', { count: result.created })}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {t('groups.broadcastTotals', {
              total: result.total_groups,
              created: result.created,
              reused: result.reused,
              skipped: result.skipped.length,
            })}
          </p>
        </div>
      </div>

      {/* Navbatda turgani — xato emas, takror xabarning oldi olingan */}
      {result.reused > 0 && (
        <Note icon={Info} tone="muted">
          {t('groups.broadcastReused', { count: result.reused })}
        </Note>
      )}

      {result.skipped.length > 0 && (
        <div className="rounded-2xl bg-warn/[0.07] p-3.5">
          <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-warn">
            <AlertTriangle className="size-3.5" />
            {t('groups.broadcastSkipped', { count: result.skipped.length })}
          </div>
          <ul className="max-h-48 space-y-2 overflow-y-auto">
            {shown.map((skip) => (
              <li key={skip.group_id} className="text-xs leading-relaxed">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{skip.title}</span>
                  {/* Kod uchun qisqa yorliq; kod noma'lum bo'lsa kodning o'zi */}
                  <Badge tone="warn">
                    {t(`groups.skipReason.${skip.reason}`, { defaultValue: skip.reason })}
                  </Badge>
                </div>
                {/* Sabab matnini backend beradi — bu yerda tarjima qilinmaydi */}
                <p className="mt-0.5 text-2xs text-muted">{skip.message}</p>
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <p className="mt-2 text-2xs text-muted">
              {t('groups.broadcastSkippedMore', { count: hidden })}
            </p>
          )}
        </div>
      )}

      <Note icon={Clock} tone="accent">
        {t('groups.broadcastQueued', { seconds: BOT_POLL_SECONDS })}
      </Note>
    </div>
  )
}

/* ── Kichik eslatma qatori ───────────────────────────────── */

const NOTE_TONE = {
  muted: 'bg-surface-2/60 text-muted',
  warn: 'bg-warn/10 text-warn',
  accent: 'bg-accent-soft text-accent',
} as const

function Note({
  icon: Icon,
  tone,
  children,
}: {
  icon: typeof Info
  tone: keyof typeof NOTE_TONE
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-2xs leading-relaxed',
        NOTE_TONE[tone],
      )}
    >
      <Icon className="mt-px size-3.5 shrink-0" />
      <span>{children}</span>
    </div>
  )
}
