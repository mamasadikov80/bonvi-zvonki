/**
 * Hududni o'chirish.
 *
 * Backend ishlatilayotgan hududni o'chirmaydi — 409 va o'zbekcha
 * tushuntirish qaytaradi. Bu XATO emas, oddiy holat: shuning uchun
 * qizil "xatolik" oynasi emas, xotirjam sariq eslatma ko'rsatiladi
 * va darhol ishlaydigan muqobil taklif qilinadi — «Faolsizlantirish».
 *
 * Ishlatilish soni allaqachon ma'lum bo'lsa, o'chirish tugmasi
 * umuman ko'rsatilmaydi: adminni rad javob oladigan tugmaga bosishga
 * majburlashning ma'nosi yo'q.
 */

import { AlertTriangle, EyeOff, Info } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  conflictMessage,
  errorMessage,
  isConflict,
  useDeleteRegion,
  usageTotal,
  useUpdateRegion,
  type Region,
} from '@/modules/regions/api'
import { Modal } from '@/shared/ui/Modal'
import { Button } from '@/shared/ui/primitives'

export function RegionDeleteModal({
  region,
  onClose,
  onDone,
}: {
  region: Region | null
  onClose: () => void
  onDone: (message: string) => void
}) {
  const { t } = useTranslation()
  const remove = useDeleteRegion()
  const update = useUpdateRegion()

  /** Backend rad etgan bo'lsa — uning o'z xabari */
  const [refusal, setRefusal] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Boshqa hudud ochilganda oldingi javoblar qolib ketmasin
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  if (!region && loadedKey !== null) setLoadedKey(null)
  if (region && region.id !== loadedKey) {
    setLoadedKey(region.id)
    setRefusal(null)
    setError(null)
  }

  const usage = region?.usage
  const total = usageTotal(usage)
  const inUse = total > 0 || refusal !== null
  const busy = remove.isPending || update.isPending

  const localRefusal = t('regions.inUse', {
    agents: usage?.agents ?? 0,
    clients: usage?.clients ?? 0,
    groups: usage?.groups ?? 0,
  })

  const doDelete = () => {
    if (!region) return
    setError(null)
    remove.mutate(region.id, {
      onSuccess: () => {
        onDone(t('regions.deleted', { name: region.name }))
        onClose()
      },
      onError: (e) => {
        // 409 — kutilgan javob. Backendning o'zbekcha matni ustun turadi.
        if (isConflict(e)) setRefusal(conflictMessage(e, localRefusal))
        else setError(errorMessage(e, t('common.error')))
      },
    })
  }

  const doDeactivate = () => {
    if (!region) return
    setError(null)
    update.mutate(
      { id: region.id, is_active: false },
      {
        onSuccess: () => {
          onDone(t('regions.deactivated', { name: region.name }))
          onClose()
        },
        onError: (e) => setError(errorMessage(e, t('common.error'))),
      },
    )
  }

  return (
    <Modal
      open={region !== null}
      onOpenChange={(open) => !open && onClose()}
      title={t('regions.deleteTitle')}
      description={region?.name}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {inUse ? (
            region?.is_active && (
              <Button disabled={busy} onClick={doDeactivate}>
                <EyeOff className="size-4" />
                {busy ? t('settings.saving') : t('regions.deactivate')}
              </Button>
            )
          ) : (
            <Button variant="danger" disabled={busy} onClick={doDelete}>
              {busy ? t('settings.saving') : t('common.delete')}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-3">
        {inUse ? (
          <>
            {/* Rad javobi — xotirjam, sariq, tushuntirish bilan */}
            <div className="animate-scale-in flex items-start gap-2.5 rounded-2xl bg-warn/[0.08] p-4 ring-1 ring-warn/25">
              <span className="icon-tile size-8 shrink-0 bg-warn/15 text-warn">
                <AlertTriangle className="size-4" />
              </span>
              <div className="min-w-0 space-y-1.5">
                <p className="text-xs leading-relaxed text-text">
                  {refusal ?? localRefusal}
                </p>
                {total > 0 && (
                  <p className="tnum text-2xs font-medium text-warn">
                    {t('regions.renameBreakdown', {
                      agents: usage?.agents ?? 0,
                      clients: usage?.clients ?? 0,
                      groups: usage?.groups ?? 0,
                    })}
                  </p>
                )}
              </div>
            </div>

            {region?.is_active ? (
              <p className="flex items-start gap-1.5 rounded-xl bg-surface-2/60 px-4 py-3 text-2xs leading-relaxed text-muted">
                <Info className="mt-px size-3 shrink-0" />
                {t('regions.deactivateHint')}
              </p>
            ) : (
              <p className="rounded-xl bg-surface-2/60 px-4 py-3 text-2xs leading-relaxed text-muted">
                {t('regions.alreadyInactive')}
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm leading-relaxed">
              {t('regions.deleteConfirm', { name: region?.name ?? '' })}
            </p>
            <p className="rounded-xl bg-surface-2/60 px-4 py-3 text-2xs leading-relaxed text-muted">
              {t('regions.deleteFree')}
            </p>
          </>
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
