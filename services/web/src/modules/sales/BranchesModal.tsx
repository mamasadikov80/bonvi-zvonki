/**
 * Filial → xodim xaritasi.
 *
 * NEGA BU EKRAN KERAK. SAP da sotuvchining ismi YO'Q — faqat
 * `Подразделение` (filial) bor. Savdo xodimga aynan shu xarita orqali
 * bog'lanadi, ya'ni xarita noto'g'ri bo'lsa butun hisobot noto'g'ri
 * odamni ko'rsatadi. Shuning uchun u yashirin sozlama emas: rahbar
 * uni ko'radi va bir bosishda tuzatadi.
 *
 * ⚠️ AVTOMATIK MOSLIK — AYNAN TENGLIK bo'yicha, fuzzy YO'Q: noto'g'ri
 * xodimga savdo yozish bo'sh qoldirishdan yomonroq. Shuning uchun
 * ro'yxatda biriktirilmagan filiallar ham turadi (`agent_id = NULL`)
 * — aks holda ularni topib biriktirish uchun joy bo'lmasdi.
 *
 * ⚠️ Qo'lda qo'yilgan xodim keyingi importlarda O'ZGARMAYDI
 * (`matched_automatically = false`). Bu ekrandagi belgining butun
 * ma'nosi: rahbar qaysi qator uning qarori, qaysi biri mashinaning
 * taxmini ekanini ko'rib turadi.
 */

import { Link2Off, TriangleAlert, UserCheck, Wand2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAgents } from '@/modules/agents/api'
import { useAssignBranch, useSaleBranches } from '@/modules/sales/api'
import { ApiError } from '@/shared/api/client'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, EmptyState, Select, Skeleton } from '@/shared/ui/primitives'

export function BranchesModal({
  open,
  onClose,
  canEdit,
}: {
  open: boolean
  onClose: () => void
  /** `sales:review` yo'q bo'lsa xarita faqat o'qish uchun ochiladi */
  canEdit: boolean
}) {
  const { t } = useTranslation()
  const branches = useSaleBranches()
  /* Faolsizlar ham keladi: tarixiy savdo arxivlangan xodimga
     bog'langan bo'lishi mumkin va tanlagichda uning ismi yo'qolsa
     qiymat jimgina o'chib ketardi. */
  const agents = useAgents(true)
  const assign = useAssignBranch()

  const [error, setError] = useState<string | null>(null)

  const options = useMemo(
    () =>
      [...(agents.data ?? [])].sort((a, b) =>
        a.full_name.localeCompare(b.full_name, 'ru'),
      ),
    [agents.data],
  )

  /* Tartib: avval biriktirilmaganlar (ular ish talab qiladi), keyin
     savdosi ko'plari. Alifbo tartibi bu yerda foydasiz — ro'yxat
     29 qator va rahbarga «nima qilish kerak» ro'yxati kerak. */
  const rows = useMemo(() => {
    return [...(branches.data ?? [])].sort((a, b) => {
      const aFree = a.agent_id ? 1 : 0
      const bFree = b.agent_id ? 1 : 0
      if (aFree !== bFree) return aFree - bFree
      return (b.sales ?? 0) - (a.sales ?? 0) || a.branch.localeCompare(b.branch, 'ru')
    })
  }, [branches.data])

  const unassigned = rows.filter((row) => !row.agent_id).length

  const change = (branch: string, agentId: string) => {
    setError(null)
    assign.mutate(
      { branch, agentId: agentId || null },
      {
        onError: (e) =>
          setError(e instanceof ApiError ? e.message : t('common.error')),
      },
    )
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t('sales.branches.title')}
      description={t('sales.branches.hint')}
      size="lg"
      footer={<Button onClick={onClose}>{t('common.close')}</Button>}
    >
      <div className="space-y-4">
        {/* Qamrov ochiq aytiladi: xarita to'liq emas va bu KUTILGAN
            holat, nosozlik emas. Sonsiz bu farq ko'rinmasdi. */}
        {!branches.isLoading && rows.length > 0 && (
          <p
            className={cn(
              'rounded-xl px-3.5 py-3 text-2xs leading-relaxed',
              unassigned ? 'bg-warn/[0.08] text-warn' : 'bg-good/10 text-good',
            )}
          >
            {unassigned
              ? t('sales.branches.unassigned', { count: unassigned, total: rows.length })
              : t('sales.branches.allAssigned', { count: rows.length })}
          </p>
        )}

        {error && (
          <div className="flex animate-scale-in items-start gap-3 rounded-2xl bg-bad/[0.08] p-3.5">
            <span className="icon-tile size-9 shrink-0 text-bad">
              <TriangleAlert className="size-4" />
            </span>
            <p className="min-w-0 text-2xs leading-relaxed text-bad">{error}</p>
          </div>
        )}

        {branches.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !rows.length ? (
          <EmptyState
            message={t('sales.branches.empty')}
            hint={t('sales.branches.emptyHint')}
          />
        ) : (
          <div className="scroll-x">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-2 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.branches.branch')}
                  </th>
                  <th className="px-2 py-2.5 text-right text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.sales')}
                  </th>
                  <th className="px-2 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.branches.match')}
                  </th>
                  <th className="px-2 py-2.5 text-2xs font-medium uppercase tracking-wider text-muted">
                    {t('sales.col.agent')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const saving =
                    assign.isPending && assign.variables?.branch === row.branch
                  return (
                    <tr
                      key={row.branch}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="px-2 py-2.5">
                        <span className="font-medium">{row.branch}</span>
                      </td>
                      <td className="tnum px-2 py-2.5 text-right text-muted">
                        {row.sales != null ? formatNumber(row.sales) : '—'}
                      </td>
                      <td className="px-2 py-2.5">
                        <MatchBadge
                          assigned={Boolean(row.agent_id)}
                          automatic={row.matched_automatically}
                        />
                      </td>
                      <td className="px-2 py-2.5">
                        <Select
                          compact
                          className="min-w-[190px]"
                          disabled={!canEdit || saving}
                          active={Boolean(row.agent_id)}
                          value={row.agent_id ?? ''}
                          onChange={(e) => change(row.branch, e.target.value)}
                        >
                          {/* Bo'sh qiymat — to'liq huquqli tanlov:
                              `Зухриддин` ataylab xodimsiz qoladi */}
                          <option value="">{t('sales.noAgent')}</option>
                          {options.map((agent) => (
                            <option key={agent.id} value={agent.id}>
                              {agent.full_name}
                              {agent.is_active ? '' : ` · ${t('regions.inactive')}`}
                            </option>
                          ))}
                        </Select>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
          {t('sales.branches.manualNote')}
        </p>
      </div>
    </Modal>
  )
}

function MatchBadge({
  assigned,
  automatic,
}: {
  assigned: boolean
  automatic: boolean
}) {
  const { t } = useTranslation()

  if (!assigned) {
    return (
      <Badge tone="warn" title={t('sales.branches.noneHint')}>
        <Link2Off className="size-3" />
        {t('sales.branches.none')}
      </Badge>
    )
  }
  if (automatic) {
    return (
      <Badge tone="neutral" title={t('sales.branches.autoHint')}>
        <Wand2 className="size-3" />
        {t('sales.branches.auto')}
      </Badge>
    )
  }
  return (
    <Badge tone="accent" title={t('sales.branches.manualHint')}>
      <UserCheck className="size-3" />
      {t('sales.branches.manual')}
    </Badge>
  )
}
