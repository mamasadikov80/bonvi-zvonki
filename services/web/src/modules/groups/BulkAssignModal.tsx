/**
 * Ommaviy tahrirlash — tanlangan guruhlarga bitta amal.
 *
 * QOIDA: tahrirlash faqat modalda. Bu yerda esa yana bir sabab bor —
 * bitta xodimda 40 ta hududsiz guruh bo'lishi mumkin, ularni birma-bir
 * ochish real ish emas. Tugundan «hammasini tanlash» → shu oyna →
 * bitta tasdiq.
 *
 * Uch amal, uchalasi ham bitta mantiqdan kelib chiqadi — guruhning
 * ishchi yoki yo'qligini HUDUD belgilaydi:
 *
 *   • hudud biriktirish       — guruhni ishga qo'shadi
 *   • hududni olib tashlash   — guruhni chetga chiqaradi (mijozsiz
 *                               ichki guruhlar aynan shunday belgilanadi)
 *   • xodimni almashtirish    — bot noto'g'ri odamni topgan bo'lsa
 *
 * Uchalasi ham guruhni `bound_by="manual"` qiladi va shundan keyin
 * avtomatik biriktirish unga UMUMAN tegmaydi. Bu oynada ochiq
 * yozilgan: admin nima yo'qotayotganini bilib bosishi kerak.
 */

import { AlertTriangle, CheckCircle2, Hand, MapPin, UserCog, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgents } from '@/modules/agents/api'
import {
  useBulkPatchGroups,
  type BulkResult,
  type GroupPatch,
  type TelegramGroup,
} from '@/modules/groups/api'
import { useRegionChoices } from '@/modules/regions/api'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, Label, Select } from '@/shared/ui/primitives'

export type BulkMode = 'region' | 'clear' | 'agent'

export function BulkAssignModal({
  open,
  groups,
  initialMode = 'region',
  onClose,
  onDone,
}: {
  open: boolean
  groups: TelegramGroup[]
  initialMode?: BulkMode
  onClose: () => void
  /** Muvaffaqiyatli tugagach tanlovni tozalash uchun */
  onDone: () => void
}) {
  const { t } = useTranslation()
  const agents = useAgents(true)
  const { names: regions } = useRegionChoices()
  const bulk = useBulkPatchGroups()

  const [mode, setMode] = useState<BulkMode>(initialMode)
  const [region, setRegion] = useState('')
  const [agentId, setAgentId] = useState('')
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<BulkResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Har ochilishda toza holat — o'tgan safargi natija yangi
  // tanlovga tegishlidek ko'rinib qolmasin
  useEffect(() => {
    if (!open) return
    setMode(initialMode)
    setRegion('')
    setAgentId('')
    setProgress(0)
    setResult(null)
    setError(null)
  }, [open, initialMode])

  const total = groups.length
  const ready =
    mode === 'clear' || (mode === 'region' ? Boolean(region) : Boolean(agentId))

  const patch = (): GroupPatch => {
    if (mode === 'region') return { region }
    // ATAYIN `null` — «yuborilmagan» dan farq qiladi, backend
    // aynan shu farqni o'qiydi va hududni bo'shatadi
    if (mode === 'clear') return { region: null }
    return { agent_id: agentId }
  }

  const run = () => {
    setError(null)
    setProgress(0)
    bulk.mutate(
      { groups, patch: patch(), onProgress: (done) => setProgress(done) },
      {
        onSuccess: (data) => {
          setResult(data)
          if (!data.failed.length) onDone()
        },
        onError: () => setError(t('common.error')),
      },
    )
  }

  const title = result
    ? t('groups.bulk.doneTitle')
    : t(`groups.bulk.title.${mode}`, { count: total })

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={title}
      description={result ? undefined : t('groups.bulk.hint', { count: total })}
      size="md"
      footer={
        result ? (
          <Button
            onClick={() => {
              if (!result.failed.length) onDone()
              onClose()
            }}
          >
            {t('common.close')}
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={bulk.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant={mode === 'clear' ? 'danger' : 'primary'}
              disabled={!ready || bulk.isPending || !total}
              onClick={run}
            >
              {bulk.isPending
                ? t('groups.bulk.running', { done: progress, total })
                : t(`groups.bulk.confirm.${mode}`, { count: total })}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <BulkResultView result={result} total={total} />
      ) : (
        <div className="space-y-4">
          {/* Amal tanlovi — uchalasi ham bitta tanlov ustida ishlaydi */}
          <div className="flex flex-wrap gap-2">
            <ModeChip
              icon={MapPin}
              active={mode === 'region'}
              label={t('groups.bulk.modeRegion')}
              onClick={() => setMode('region')}
            />
            <ModeChip
              icon={X}
              active={mode === 'clear'}
              label={t('groups.bulk.modeClear')}
              onClick={() => setMode('clear')}
            />
            <ModeChip
              icon={UserCog}
              active={mode === 'agent'}
              label={t('groups.bulk.modeAgent')}
              onClick={() => setMode('agent')}
            />
          </div>

          {mode === 'region' && (
            <div>
              <Label>{t('groups.regionField')}</Label>
              <Select
                autoFocus
                value={region}
                onChange={(event) => setRegion(event.target.value)}
              >
                <option value="">{t('groups.bulk.pickRegion')}</option>
                {regions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {mode === 'agent' && (
            <div>
              <Label>{t('groups.agentField')}</Label>
              <Select
                autoFocus
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
              >
                <option value="">{t('groups.bulk.pickAgent')}</option>
                {(agents.data ?? []).map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.is_active
                      ? agent.full_name
                      : `${agent.full_name} · ${t('groups.inactive')}`}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {mode === 'clear' && (
            <p className="rounded-xl bg-warn/[0.09] px-4 py-3 text-2xs leading-relaxed text-warn">
              {t('groups.bulk.clearExplain')}
            </p>
          )}

          {/* Kimga tegadi — ro'yxat ochiq, «ishonavering» emas */}
          <div className="rounded-2xl bg-surface-2/60 p-3.5">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-2xs font-medium uppercase tracking-wider text-muted">
                {t('groups.bulk.affected')}
              </span>
              <span className="tnum text-2xs font-semibold">{formatNumber(total)}</span>
            </div>
            <ul className="max-h-44 space-y-1 overflow-y-auto">
              {groups.map((group) => (
                <li
                  key={group.id}
                  className="flex items-center gap-2 text-xs leading-relaxed"
                >
                  <span className="size-1.5 shrink-0 rounded-full bg-accent" />
                  <span className="truncate font-medium">{group.title}</span>
                  <span className="ml-auto shrink-0 truncate text-2xs text-muted">
                    {group.region ?? t('groups.tree.regionlessShort')}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Avtomatikadan chiqish — eng muhim oqibat */}
          <p className="flex items-start gap-2 rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            <Hand className="mt-px size-3.5 shrink-0" />
            {t('groups.bulk.manualWarning')}
          </p>

          {bulk.isPending && <Progress done={progress} total={total} />}

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

/* ── Amal chipi ──────────────────────────────────────────── */

function ModeChip({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: typeof MapPin
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium',
        'transition-all duration-250 ease-ios active:scale-[0.97]',
        active ? 'bg-accent text-white shadow-xs' : 'bg-surface-2 text-muted hover:text-text',
      )}
    >
      <Icon className="size-3.5" />
      {label}
    </button>
  )
}

/* ── Jarayon ─────────────────────────────────────────────────
   Backendda ommaviy endpoint yo'q — panel PATCH larni bo'lib
   yuboradi. 40 ta so'rov bir necha soniya davom etadi, shuning
   uchun holat ko'rinib turishi kerak. */

function Progress({ done, total }: { done: number; total: number }) {
  const { t } = useTranslation()
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-2xs text-muted">
        <span>{t('groups.bulk.progress')}</span>
        <span className="tnum">
          {done} / {total}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-250 ease-ios"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/* ── Natija ──────────────────────────────────────────────── */

function BulkResultView({ result, total }: { result: BulkResult; total: number }) {
  const { t } = useTranslation()
  const clean = result.failed.length === 0

  return (
    <div className="space-y-4">
      <div
        className={cn(
          'flex items-start gap-3 rounded-2xl p-4',
          clean ? 'bg-good/10' : 'bg-warn/[0.08]',
        )}
      >
        <span
          className={cn('icon-tile size-10 shrink-0', clean ? 'text-good' : 'text-warn')}
        >
          {clean ? (
            <CheckCircle2 className="size-5" />
          ) : (
            <AlertTriangle className="size-5" />
          )}
        </span>
        <div className="min-w-0">
          <p
            className={cn(
              'text-sm font-semibold',
              clean ? 'text-good' : 'text-warn',
            )}
          >
            {t('groups.bulk.updated', { count: result.updated })}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {t('groups.bulk.totals', {
              total,
              updated: result.updated,
              failed: result.failed.length,
            })}
          </p>
        </div>
      </div>

      {result.failed.length > 0 && (
        <div className="rounded-2xl bg-bad/[0.07] p-3.5">
          <div className="mb-2 flex items-center gap-1.5 text-2xs font-medium text-bad">
            <AlertTriangle className="size-3.5" />
            {t('groups.bulk.failed', { count: result.failed.length })}
          </div>
          <ul className="max-h-48 space-y-2 overflow-y-auto">
            {result.failed.map((item) => (
              <li key={item.title} className="text-xs leading-relaxed">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {t('groups.bulk.failedChunk', {
                      title: item.title,
                      count: item.count,
                    })}
                  </span>
                  <Badge tone="bad">{t('groups.bulk.failedBadge')}</Badge>
                </div>
                <p className="mt-0.5 text-2xs text-muted">{item.message}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
