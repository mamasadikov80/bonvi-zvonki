/**
 * Xodimlarni tizimdan olib tashlash — tasdiqlash oynasi.
 *
 * ⚠️ MA'LUMOT HECH QACHON YO'QOLMAYDI. `calls.agent_id` da
 * `ON DELETE CASCADE` bor: xodim qatori o'chsa, uning qo'ng'iroqlari,
 * transkriptlari va BAHOLARI ham o'chib ketardi. Shuning uchun tizimda
 * bunday yo'l umuman yo'q va bu oynada «baribir o'chirish» tugmasi
 * ham yo'q — bosib qo'yish mumkin bo'lgan xato yaratilmagan.
 *
 * Har bir xodim uchun qaror AVTOMATIK:
 *   · bo'sh xodim         → qatori butunlay o'chadi;
 *   · ma'lumoti bor xodim → arxivga o'tadi, ma'lumoti saqlanadi.
 *
 * Oyna shuni oldindan, aniq sonlar bilan ko'rsatadi.
 */

import { Archive, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import {
  useDeleteAgents,
  useDeletionImpact,
  type DeletionImpact,
} from '@/modules/agents/api'
import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Button, Skeleton } from '@/shared/ui/primitives'

export function DeleteAgentsModal({
  open,
  agentIds,
  onClose,
  onDone,
}: {
  open: boolean
  agentIds: string[]
  onClose: () => void
  /** O'chirish tugagach — tanlovni tozalash uchun */
  onDone: (deleted: number) => void
}) {
  const { t } = useTranslation()
  const impact = useDeletionImpact()
  const remove = useDeleteAgents()

  const { mutate: loadImpact, reset: resetImpact } = impact
  const { reset: resetRemove } = remove

  useEffect(() => {
    if (!open || agentIds.length === 0) return
    resetRemove()
    loadImpact(agentIds)
    return () => resetImpact()
  }, [open, agentIds, loadImpact, resetImpact, resetRemove])

  const rows = impact.data ?? []
  const safe = rows.filter((row) => row.safe)
  const risky = rows.filter((row) => !row.safe)
  const done = remove.data

  const run = () =>
    remove.mutate(agentIds, {
      onSuccess: (result) => onDone(result.deleted.length + result.archived.length),
    })

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t('agents.delete.title', { count: agentIds.length })}
      description={done ? undefined : t('agents.delete.hint')}
      size="md"
      footer={
        done ? (
          <Button onClick={onClose}>{t('common.close')}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={remove.isPending}>
              {t('common.cancel')}
            </Button>
            {rows.length > 0 && (
              <Button variant="danger" disabled={remove.isPending} onClick={run}>
                <Trash2 className="size-4" />
                {t('agents.delete.confirm', { count: rows.length })}
              </Button>
            )}
          </>
        )
      }
    >
      {impact.isPending ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : done ? (
        <ResultView message={done.message} archived={done.archived} />
      ) : (
        <div className="space-y-4">
          {/* Xavfsizlar — bemalol o'chadi */}
          {safe.length > 0 && (
            <section>
              <Header
                tone="good"
                icon={ShieldCheck}
                title={t('agents.delete.safeTitle', { count: safe.length })}
                hint={t('agents.delete.safeHint')}
              />
              <NameList rows={safe} />
            </section>
          )}

          {/* Arxivga o'tadiganlar — nimasi saqlanishi bilan */}
          {risky.length > 0 && (
            <section>
              <Header
                tone="warn"
                icon={Archive}
                title={t('agents.delete.archiveTitle', { count: risky.length })}
                hint={t('agents.delete.archiveHint')}
              />
              <ul className="mt-2 space-y-2">
                {risky.map((row) => (
                  <li
                    key={row.agent_id}
                    className="rounded-xl bg-surface-2/60 px-3.5 py-3"
                  >
                    <div className="text-xs font-medium">{row.full_name}</div>
                    <ul className="mt-1 space-y-0.5">
                      {row.blockers.map((reason, index) => (
                        <li key={index} className="text-2xs leading-relaxed text-muted">
                          · {reason}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rows.length === 0 && (
            <p className="text-xs text-muted">{t('agents.delete.nothing')}</p>
          )}

          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('agents.delete.alternative')}
          </p>

          {remove.isError && (
            <p className="rounded-xl bg-bad/[0.08] px-3.5 py-3 text-2xs text-bad">
              {remove.error instanceof ApiError
                ? remove.error.message
                : t('common.error')}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}

function Header({
  tone,
  icon: Icon,
  title,
  hint,
}: {
  tone: 'good' | 'warn'
  icon: typeof ShieldCheck
  title: string
  hint: string
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className={cn(
          'icon-tile size-8 shrink-0',
          tone === 'good' ? 'bg-good/10 text-good' : 'bg-warn/10 text-warn',
        )}
      >
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0">
        <div className="text-xs font-medium">{title}</div>
        <p className="text-2xs leading-relaxed text-muted">{hint}</p>
      </div>
    </div>
  )
}

function NameList({ rows }: { rows: DeletionImpact[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {rows.map((row) => (
        <span
          key={row.agent_id}
          className="rounded-lg bg-surface-2 px-2 py-1 text-2xs text-muted"
        >
          {row.full_name}
        </span>
      ))}
    </div>
  )
}

function ResultView({
  message,
  archived,
}: {
  message: string
  archived: DeletionImpact[]
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      {/* Backendning o'zbekcha xulosasi — o'zgartirilmaydi */}
      <p className="rounded-xl bg-good/10 px-3.5 py-3 text-xs leading-relaxed text-good">
        {message}
      </p>

      {archived.length > 0 && (
        <div>
          <p className="mb-1.5 text-2xs text-muted">
            {t('agents.delete.keptTitle', { count: archived.length })}
          </p>
          <NameList rows={archived} />
        </div>
      )}
    </div>
  )
}
