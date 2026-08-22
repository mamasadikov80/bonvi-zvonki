/**
 * SAP eksportini yuklash.
 *
 * FAYL TURI TANLANMAYDI. Uchta har xil eksport keladi (operatsiyalar
 * registri, kontragentlar katalogi, balans hisoboti) va ularni
 * backend SARLAVHA bo'yicha o'zi taniydi. Ekranda «tur» tanlagichi
 * bo'lganida u faqat xato manbai bo'lardi: noto'g'ri tanlangan fayl
 * jimgina noto'g'ri jadvalga tushardi.
 *
 * ⚠️ IMPORT TARTIBI ERKIN. Registr katalogdan oldin yuklansa savdolar
 * telefonsiz qoladi va ro'yxat BO'SH ko'rinadi — ya'ni «hammasi
 * joyida» degan yolg'on ma'no beradi. Katalog kelganda backend
 * bog'lanishlarni tiklaydi (`linked_sales`), shuning uchun hisobotda
 * aynan shu son alohida ko'rsatiladi.
 */

import {
  CheckCircle2,
  FileSpreadsheet,
  TriangleAlert,
  Upload,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useImportSales, type SalesImportReport } from '@/modules/sales/api'
import { ApiError } from '@/shared/api/client'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, Skeleton } from '@/shared/ui/primitives'

/** Brauzer dialogida ko'rinadigan fayllar. Faqat `.xlsx`: backend
 *  `openpyxl` bilan o'qiydi va eski `.xls` ni umuman ochmaydi. */
const ACCEPT = '.xlsx'

export function ImportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const upload = useImportSales()
  const inputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<SalesImportReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Har ochilishda toza holat — o'tgan safargi hisobot yangi faylga
  // tegishlidek ko'rinib qolmasin
  useEffect(() => {
    if (!open) return
    setFile(null)
    setReport(null)
    setError(null)
    upload.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const run = () => {
    if (!file) return
    setError(null)
    upload.mutate(file, {
      onSuccess: setReport,
      onError: (e) => setError(e instanceof ApiError ? e.message : t('common.error')),
    })
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={report ? t('sales.import.doneTitle') : t('sales.import.title')}
      description={report ? undefined : t('sales.import.hint')}
      size="md"
      footer={
        report ? (
          <>
            {/* Uchta fayl ketma-ket yuklanadi — modalni yopib qayta
                ochish o'rniga shu yerdan davom etish mumkin */}
            <Button
              variant="secondary"
              onClick={() => {
                setFile(null)
                setReport(null)
                setError(null)
              }}
            >
              {t('sales.import.another')}
            </Button>
            <Button onClick={onClose}>{t('common.close')}</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={upload.isPending}>
              {t('common.cancel')}
            </Button>
            <Button disabled={!file || upload.isPending} onClick={run}>
              {upload.isPending ? t('sales.import.running') : t('sales.import.start')}
            </Button>
          </>
        )
      }
    >
      {report ? (
        <ImportReportView report={report} />
      ) : (
        <div className="space-y-4">
          {/* Fayl tanlash. `<input type="file">` ning o'zi ko'rinmaydi:
              uning standart ko'rinishi mavzuga bo'ysunmaydi va qorong'i
              rejimda o'qilmaydi. Bosiladigan maydon esa katta —
              sichqonchani aniq nishonga olish shart emas. */}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={cn(
              'flex w-full items-center gap-3 rounded-2xl p-4 text-left',
              'ring-1 ring-inset transition-all duration-250 ease-ios active:scale-[0.99]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
              file
                ? 'bg-accent-soft ring-accent/30'
                : 'bg-surface-2 ring-border hover:ring-border/80',
            )}
          >
            <span
              className={cn(
                'icon-tile size-10 shrink-0',
                file ? 'text-accent' : 'text-muted',
              )}
            >
              {file ? (
                <FileSpreadsheet className="size-5" />
              ) : (
                <Upload className="size-5" />
              )}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-xs font-medium">
                {file ? file.name : t('sales.import.choose')}
              </span>
              <span className="mt-0.5 block text-2xs text-muted">
                {file
                  ? t('sales.import.size', {
                      value: (file.size / 1024 / 1024).toFixed(2),
                    })
                  : t('sales.import.chooseHint')}
              </span>
            </span>
          </button>

          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setError(null)
              /* Qiymat tozalanadi: aks holda bir xil faylni ikkinchi
                 marta tanlaganda `change` umuman ishlamasdi */
              e.target.value = ''
            }}
          />

          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('sales.import.kindNote')}
          </p>

          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('sales.import.idempotentNote')}
          </p>

          {upload.isPending && (
            <div className="space-y-2">
              <p className="text-2xs text-muted">{t('sales.import.runningHint')}</p>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          )}

          {error && (
            <div className="flex animate-scale-in items-start gap-3 rounded-2xl bg-bad/[0.08] p-3.5">
              <span className="icon-tile size-9 shrink-0 text-bad">
                <TriangleAlert className="size-4" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium text-bad">
                  {t('sales.import.failed')}
                </p>
                {/* Backendning o'zbekcha xabari — u faylning NIMA
                    ekanini ham aytadi («bu balans hisoboti»), shuning
                    uchun o'zgartirilmaydi */}
                <p className="mt-0.5 text-2xs leading-relaxed text-muted">{error}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

/* ── Hisobot ─────────────────────────────────────────────────
   Har son ALOHIDA savolga javob beradi va ular qo'shilmaydi:
   «o'qildi» — fayldagi qatorlar, «yangi/yangilandi» — bazaga
   tushganlari, qolganlari — nuqsonlar. Shuning uchun ular bitta
   yig'indi qatoriga siqilmaydi. */

function ImportReportView({ report }: { report: SalesImportReport }) {
  const { t } = useTranslation()
  const clean =
    report.skipped === 0 &&
    report.unknown_partner === 0 &&
    report.unmatched_branches.length === 0

  const rows: { key: keyof SalesImportReport; tone?: 'good' | 'muted' }[] = [
    { key: 'read' },
    { key: 'created', tone: 'good' },
    { key: 'updated' },
    { key: 'skipped', tone: 'muted' },
    { key: 'unknown_partner', tone: 'muted' },
    { key: 'unknown_op_type', tone: 'muted' },
  ]

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
            <TriangleAlert className="size-5" />
          )}
        </span>
        <div className="min-w-0">
          <p className={cn('text-sm font-semibold', clean ? 'text-good' : 'text-warn')}>
            {t('sales.import.created', { count: report.created })}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {t('sales.import.kindLine', {
              kind: t(`sales.import.kind.${report.kind}`, {
                defaultValue: report.kind,
              }),
              file: report.source,
            })}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {rows.map((row) => {
          const value = report[row.key] as number
          return (
            <div key={row.key} className="rounded-xl bg-surface-2/60 px-3.5 py-3">
              {/* ⚠️ `stat.` prefiksi ataylab: `sales.import.created`
                  allaqachon band — u sarlavhadagi «N ta yangi savdo»
                  jumlasi. Kartochkada esa faqat qisqa yorliq kerak. */}
              <div className="text-2xs text-muted">
                {t(`sales.import.stat.${row.key}`)}
              </div>
              <div
                className={cn(
                  'tnum mt-0.5 text-lg font-semibold',
                  row.tone === 'good' && value > 0 && 'text-good',
                  row.tone === 'muted' && value > 0 && 'text-warn',
                )}
              >
                {formatNumber(value)}
              </div>
            </div>
          )
        })}
      </div>

      {/* Katalog kelgach tiklangan bog'lanishlar. Nol bo'lsa
          ko'rsatilmaydi — u faqat «registr oldin yuklangan» holatda
          ma'noli, boshqa paytda shovqin bo'lardi. */}
      {report.linked_sales > 0 && (
        <p className="rounded-xl bg-good/10 px-3.5 py-3 text-2xs leading-relaxed text-good">
          {t('sales.import.linkedSales', { count: report.linked_sales })}
        </p>
      )}

      {report.phones_filled > 0 && (
        <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
          {t('sales.import.phonesFilled', { count: report.phones_filled })}
        </p>
      )}

      {/* Filiallar SON bilan emas, NOMLARI bilan: «7 ta filial
          biriktirilmadi» xabari bilan hech nima qilib bo'lmaydi,
          nomlar bilan esa darhol ish boshlanadi */}
      {report.unmatched_branches.length > 0 && (
        <div className="rounded-2xl bg-warn/[0.08] p-3.5">
          <div className="mb-2 text-2xs font-medium text-warn">
            {t('sales.import.unmatchedBranches', {
              count: report.unmatched_branches.length,
            })}
          </div>
          <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
            {report.unmatched_branches.map((branch) => (
              <Badge key={branch} tone="warn">
                {branch}
              </Badge>
            ))}
          </div>
          <p className="mt-2 text-2xs leading-relaxed text-muted">
            {t('sales.import.unmatchedHint')}
          </p>
        </div>
      )}
    </div>
  )
}
