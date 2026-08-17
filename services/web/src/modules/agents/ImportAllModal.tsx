/**
 * MoyZvonki'dagi BARCHA xodimni olish — bitta tugma.
 *
 * ⚠️ ENG MUHIM VA'DA: MAVJUDLARGA TEGILMAYDI.
 * Admin xodimning ismini tuzatgan, hududini qo'ygan, rasm yuklagan
 * bo'lishi mumkin — takroriy import bularning hech birini qayta
 * yozmaydi. Faqat yetishmayotgani yaratiladi. Shu sababli tugmani
 * necha marta bosish xavfsiz va oynada bu ochiq aytiladi: aks holda
 * admin «bosaymi yoki yo'q?» deb ikkilanib turadi.
 *
 * Telefon raqami ixtiyoriy: uni aniqlash uchun oxirgi kunlarning
 * qo'ng'iroqlari skanerlanadi va bu bir necha soniya oladi. Raqam
 * Telegram orqali ro'yxatdan o'tish uchun kerak, shuning uchun
 * standart holatda YOQILGAN.
 */

import { CheckCircle2, RefreshCw, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useImportAllAgents } from '@/modules/agents/api'
import { ApiError } from '@/shared/api/client'
import { formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Button, Skeleton, Switch } from '@/shared/ui/primitives'

export function ImportAllModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const run = useImportAllAgents()
  const [detectPhones, setDetectPhones] = useState(true)

  const { reset } = run
  useEffect(() => {
    if (open) reset()
  }, [open, reset])

  const result = run.data

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t('agents.importAll.title')}
      description={result ? undefined : t('agents.importAll.hint')}
      size="md"
      footer={
        result ? (
          <Button onClick={onClose}>{t('common.close')}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={run.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={run.isPending}
              onClick={() => run.mutate({ detectPhones })}
            >
              <RefreshCw className="size-4" />
              {run.isPending
                ? t('agents.importAll.running')
                : t('agents.importAll.start')}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-2xl bg-good/10 p-4">
            <span className="icon-tile size-10 shrink-0 text-good">
              <CheckCircle2 className="size-5" />
            </span>
            {/* Backendning o'zbekcha xulosasi — o'zgartirilmaydi */}
            <p className="text-xs leading-relaxed text-muted">{result.message}</p>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label={t('agents.importAll.total')} value={result.total} />
            <Stat label={t('agents.importAll.created')} value={result.created} tone />
            <Stat label={t('agents.importAll.linked')} value={result.linked} />
            <Stat label={t('agents.importAll.skipped')} value={result.skipped} />
          </div>

          {result.created_names.length > 0 && (
            <div>
              <p className="mb-1.5 text-2xs text-muted">
                {t('agents.importAll.newNames')}
              </p>
              <div className="flex max-h-44 flex-wrap gap-1.5 overflow-y-auto">
                {result.created_names.map((name) => (
                  <span
                    key={name}
                    className="rounded-lg bg-surface-2 px-2 py-1 text-2xs text-muted"
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('agents.importAll.afterHint')}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-2xl bg-surface-2/60 p-4">
            <span className="icon-tile size-10 shrink-0 text-muted">
              <Users className="size-5" />
            </span>
            <p className="text-2xs leading-relaxed text-muted">
              {t('agents.importAll.safeHint')}
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-medium">
                {t('agents.importAll.detectPhones')}
              </div>
              <p className="mt-0.5 text-2xs leading-relaxed text-muted">
                {t('agents.importAll.detectPhonesHint')}
              </p>
            </div>
            <Switch
              checked={detectPhones}
              disabled={run.isPending}
              label={t('agents.importAll.detectPhones')}
              onChange={setDetectPhones}
            />
          </div>

          {/* Uzoq davom etishi mumkin — spinner emas, skelet */}
          {run.isPending && (
            <div className="space-y-2">
              <p className="text-2xs text-muted">{t('agents.importAll.runningHint')}</p>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          )}

          {run.isError && (
            <p className="rounded-xl bg-bad/[0.08] px-3.5 py-3 text-2xs leading-relaxed text-bad">
              {run.error instanceof ApiError ? run.error.message : t('common.error')}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: boolean
}) {
  return (
    <div className="rounded-xl bg-surface-2/60 px-3.5 py-3">
      <div className="text-2xs text-muted">{label}</div>
      <div
        className={
          'tnum mt-0.5 text-lg font-semibold' +
          (tone && value > 0 ? ' text-good' : '')
        }
      >
        {formatNumber(value)}
      </div>
    </div>
  )
}
