/**
 * «Xodim botga ulanmagan» — sabab va yechim.
 *
 * NEGA BU KERAK: Telegram Bot API a'zoning telefon raqamini
 * KO'RSATMAYDI. Yagona yo'l — xodimning o'zi «raqamimni yuborish»
 * tugmasini bosishi. Shu bir marta bosilmasa, botning guruhda kimni
 * ko'rgani hech qanday xodimga ulanmaydi va u xodimning butun shoxi
 * bo'sh turadi.
 *
 * Bo'sh shox — jimgina nosozlik: hech qayerda xato chiqmaydi, admin
 * esa «nega bu odamda guruh yo'q?» degan savolga javob topa olmaydi.
 * Shuning uchun sabab ham, yechim ham aynan o'sha bo'sh joyda yoziladi.
 */

import { Info, Smartphone } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Button } from '@/shared/ui/primitives'

/** Daraxt tugunidagi qisqa izoh */
export function EnrollmentNotice({
  name,
  className,
}: {
  name: string
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-xl bg-warn/[0.09] px-3.5 py-3',
        className,
      )}
    >
      <span className="icon-tile size-8 shrink-0 bg-warn/15 text-warn">
        <Smartphone className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-2xs font-medium text-warn">
          {t('groups.enroll.title', { name })}
        </p>
        <p className="mt-1 text-2xs leading-relaxed text-muted">
          {t('groups.enroll.what')}
        </p>
      </div>
    </div>
  )
}

/* ── To'liq ko'rsatma ────────────────────────────────────────
   Uchta qadam. Uzun matn emas — xodimga telefon orqali aytib
   beriladigan darajada qisqa. */

export function EnrollmentModal({
  open,
  onClose,
  names = [],
}: {
  open: boolean
  onClose: () => void
  /** Kimlar hali ulanmagan — admin kimga qo'ng'iroq qilishini bilsin */
  names?: string[]
}) {
  const { t } = useTranslation()
  const steps = [
    t('groups.enroll.step1'),
    t('groups.enroll.step2'),
    t('groups.enroll.step3'),
  ]

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={t('groups.enroll.modalTitle')}
      description={t('groups.enroll.modalHint')}
      size="md"
      footer={<Button onClick={onClose}>{t('common.close')}</Button>}
    >
      <div className="space-y-4">
        <ol className="space-y-2">
          {steps.map((step, index) => (
            <li
              key={index}
              className="flex items-start gap-3 rounded-2xl bg-surface-2/60 p-3.5"
            >
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-2xs font-semibold text-accent">
                {index + 1}
              </span>
              <span className="text-xs leading-relaxed text-text">{step}</span>
            </li>
          ))}
        </ol>

        <p className="flex items-start gap-2 rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
          <Info className="mt-px size-3.5 shrink-0" />
          {t('groups.enroll.why')}
        </p>

        {names.length > 0 && (
          <div className="rounded-2xl bg-warn/[0.07] p-3.5">
            <div className="mb-2 text-2xs font-medium uppercase tracking-wider text-warn">
              {t('groups.enroll.pendingTitle', { count: names.length })}
            </div>
            <ul className="max-h-48 space-y-1 overflow-y-auto">
              {names.map((name) => (
                <li key={name} className="text-xs leading-relaxed">
                  {name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
