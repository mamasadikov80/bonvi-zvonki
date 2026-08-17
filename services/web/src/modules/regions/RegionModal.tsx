/**
 * Hudud qo'shish / tahrirlash — QOIDA bo'yicha faqat modalda.
 *
 * Eng muhim qismi — nomni o'zgartirish ogohlantirishi. Hudud xodim,
 * mijoz va guruhlarda MATN bo'lib yotibdi, shuning uchun nom o'zgarsa
 * backend uchala jadvalni ham yangilaydi. Admin buni saqlashdan OLDIN
 * bilishi kerak: nechta yozuv tegilishi aniq son bilan aytiladi.
 */

import { AlertTriangle, ArrowRight, Info } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  conflictMessage,
  isConflict,
  useArchivePreview,
  useCreateRegion,
  usageTotal,
  useUpdateRegion,
  type Region,
  type RegionInput,
} from '@/modules/regions/api'
import { cn } from '@/shared/lib/utils'
import { Modal, ModalFields } from '@/shared/ui/Modal'
import { Button, Input, Label, Switch } from '@/shared/ui/primitives'

interface Form {
  name: string
  sort_order: string
  note: string
  is_active: boolean
  /** Arxivlashda faol guruhlardan uzilsinmi */
  detach_groups: boolean
}

const EMPTY: Form = {
  name: '',
  sort_order: '0',
  note: '',
  is_active: true,
  detach_groups: true,
}

export function RegionModal({
  target,
  onClose,
  onDone,
}: {
  target: Region | 'new' | null
  onClose: () => void
  /** Sahifada ko'rsatiladigan xotirjam xabar */
  onDone: (message: string) => void
}) {
  const { t } = useTranslation()
  const isNew = target === 'new'
  const existing = target && target !== 'new' ? target : null

  const [form, setForm] = useState<Form>(EMPTY)
  const [error, setError] = useState<string | null>(null)

  // Modal ochilganda forma to'ldiriladi, yopilganda kalit tozalanadi —
  // qayta ochilganda eski qiymat qolib ketmasin
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const key = isNew ? 'new' : (existing?.id ?? null)
  if (!target && loadedKey !== null) setLoadedKey(null)
  if (key && key !== loadedKey) {
    setLoadedKey(key)
    setError(null)
    setForm(
      existing
        ? {
            name: existing.name,
            sort_order: String(existing.sort_order),
            note: existing.note ?? '',
            is_active: existing.is_active,
            // ⚠️ Standart YOQILGAN. Arxivlashdan maqsad — bu hududga
            // endi xizmat ko'rsatmaslik, demak guruhlarning uzilishi
            // KUTILGAN natija. Belgilanmagan holda qoldirilganda admin
            // hududni «o'chirdim» deb o'ylardi, guruhlar esa eski
            // hududda qolib, so'rovnoma olishda davom etardi.
            // Xavfsizlik nusxada: tarix baribir o'zgarmaydi, shuning
            // uchun ehtiyot uchun o'chirib qo'yishning ma'nosi yo'q.
            detach_groups: true,
          }
        : EMPTY,
    )
  }

  const create = useCreateRegion()
  const update = useUpdateRegion()

  // Arxivlash oqibati — faqat o'chirishga o'tilayotganda so'raladi,
  // aks holda har oyna ochilganda keraksiz so'rov ketardi
  const archivingNow = Boolean(existing?.is_active) && !form.is_active
  const preview = useArchivePreview(existing?.id ?? null, archivingNow)
  const activeGroups = preview.data?.active_groups ?? 0
  const busy = create.isPending || update.isPending

  const name = form.name.trim()
  const valid = name.length >= 2
  const total = usageTotal(existing?.usage)
  const renaming = Boolean(existing && name && name !== existing.name)
  const cascading = renaming && total > 0

  const submit = () => {
    setError(null)
    const order = Number.parseInt(form.sort_order, 10)
    const sort_order = Number.isFinite(order) ? order : 0
    const note = form.note.trim() || null

    if (!existing) {
      create.mutate(
        { name, sort_order, note },
        {
          onSuccess: (region) => {
            onDone(t('regions.created', { name: region.name }))
            onClose()
          },
          onError: (e) =>
            setError(
              isConflict(e)
                ? conflictMessage(e, t('regions.duplicate'))
                : conflictMessage(e, t('common.error')),
            ),
        },
      )
      return
    }

    // Faqat o'zgargani yuboriladi — tegilmagan nom kaskadni bekorga qo'zg'atmasin
    const patch: RegionInput = {}
    if (name !== existing.name) patch.name = name
    if (sort_order !== existing.sort_order) patch.sort_order = sort_order
    if (note !== existing.note) patch.note = note
    if (form.is_active !== existing.is_active) {
      patch.is_active = form.is_active
      // Arxivlashda tanlov ALBATTA yuboriladi — `true` ham, `false` ham.
      // Serverda standart «uzish», shuning uchun «qoldirish» aytilmasa
      // sodir bo'lmaydi.
      if (!form.is_active) patch.detach_groups = form.detach_groups
    }

    if (!Object.keys(patch).length) {
      onClose()
      return
    }

    update.mutate(
      { id: existing.id, ...patch },
      {
        onSuccess: (region) => {
          const renamed = region.renamed
          onDone(
            renamed
              ? t('regions.renamedNotice', {
                  name: region.name,
                  agents: renamed.agents,
                  clients: renamed.clients,
                  groups: renamed.groups,
                })
              : t('regions.saved', { name: region.name }),
          )
          onClose()
        },
        onError: (e) =>
          setError(
            isConflict(e)
              ? conflictMessage(e, t('regions.duplicate'))
              : conflictMessage(e, t('common.error')),
          ),
      },
    )
  }

  return (
    <Modal
      open={target !== null}
      onOpenChange={(open) => !open && onClose()}
      title={isNew ? t('regions.create') : t('regions.edit')}
      description={existing?.name}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!valid || busy} onClick={submit}>
            {busy
              ? t('settings.saving')
              : cascading
                ? t('regions.renameAction')
                : t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ModalFields>
          <div className="sm:col-span-2">
            <Label>{t('regions.name')}</Label>
            <Input
              autoFocus
              value={form.name}
              placeholder={t('regions.namePlaceholder')}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <p className="mt-1.5 flex items-start gap-1.5 text-2xs leading-relaxed text-muted">
              <Info className="mt-px size-3 shrink-0" />
              {t('regions.nameHint')}
            </p>
          </div>

          <div>
            <Label>{t('regions.order')}</Label>
            <Input
              type="number"
              className="tnum"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
            />
            <p className="mt-1.5 text-2xs text-muted">{t('regions.orderHint')}</p>
          </div>

          <div>
            <Label>{t('regions.note')}</Label>
            <Input
              value={form.note}
              placeholder={t('regions.notePlaceholder')}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
            <p className="mt-1.5 text-2xs text-muted">{t('regions.noteHint')}</p>
          </div>
        </ModalFields>

        {/* ── Nom o'zgarmoqda: kaskadni saqlashdan oldin aytamiz ── */}
        {renaming && (
          <div
            className={cn(
              'animate-scale-in rounded-2xl p-4',
              cascading ? 'bg-warn/[0.08] ring-1 ring-warn/25' : 'bg-surface-2/60',
            )}
          >
            <div className="flex items-start gap-2.5">
              <span
                className={cn(
                  'icon-tile size-8 shrink-0',
                  cascading ? 'bg-warn/15 text-warn' : 'text-muted',
                )}
              >
                {cascading ? (
                  <AlertTriangle className="size-4" />
                ) : (
                  <Info className="size-4" />
                )}
              </span>
              <div className="min-w-0 space-y-2">
                <div className="text-sm font-semibold">{t('regions.renameTitle')}</div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-lg bg-surface px-2 py-1 font-medium line-through opacity-70">
                    {existing?.name}
                  </span>
                  <ArrowRight className="size-3.5 shrink-0 text-muted" />
                  <span className="rounded-lg bg-surface px-2 py-1 font-medium">
                    {name}
                  </span>
                </div>

                {cascading ? (
                  <>
                    <p className="text-xs leading-relaxed text-text">
                      {t('regions.renameWarn', { count: total })}
                    </p>
                    <p className="tnum text-2xs font-medium text-warn">
                      {t('regions.renameBreakdown', {
                        agents: existing?.usage?.agents ?? 0,
                        clients: existing?.usage?.clients ?? 0,
                        groups: existing?.usage?.groups ?? 0,
                      })}
                    </p>
                  </>
                ) : (
                  <p className="text-xs leading-relaxed text-muted">
                    {t('regions.renameFree')}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Faollik — faqat tahrirlashda */}
        {existing && (
          <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-2/60 p-3">
            <div className="min-w-0">
              <div className="text-sm font-medium">{t('regions.active')}</div>
              <p className="text-2xs leading-relaxed text-muted">
                {t('regions.activeHint')}
              </p>
            </div>
            <Switch
              checked={form.is_active}
              label={t('regions.active')}
              onChange={(next) => setForm({ ...form, is_active: next })}
            />
          </div>
        )}

        {/* Arxivlash oqibati — FAQAT o'chirishga o'tayotganda va faol
            guruh bo'lganda. Aks holda bu blok shovqin bo'lardi. */}
        {existing && existing.is_active && !form.is_active && activeGroups > 0 && (
          <div className="animate-scale-in space-y-3 rounded-xl bg-warn/10 p-3.5 ring-1 ring-warn/25">
            <p className="text-xs leading-relaxed">
              {t('regions.archiveWarning', { count: activeGroups })}
            </p>
            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-[hsl(var(--warn))]"
                checked={form.detach_groups}
                onChange={(e) =>
                  setForm({ ...form, detach_groups: e.target.checked })
                }
              />
              <span className="text-2xs leading-relaxed">
                <span className="font-medium">
                  {t('regions.detachGroups', { count: activeGroups })}
                </span>
                <br />
                {t('regions.detachHint')}
              </span>
            </label>
          </div>
        )}

        {error && (
          <p className="animate-scale-in rounded-xl bg-bad/10 px-4 py-3 text-xs leading-relaxed text-bad">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
