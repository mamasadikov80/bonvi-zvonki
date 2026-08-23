/**
 * SAP eksportini yuklash — IKKI BOSQICHLI.
 *
 *   1. fayl tanlanadi → `POST /sales/import/preview` (BAZAGA
 *      YOZMAYDI, faqat hisoblaydi);
 *   2. hisob-kitob ko'rsatiladi → foydalanuvchi tasdiqlaydi →
 *      O'SHA fayl `POST /sales/import` ga boradi;
 *   3. natija hisoboti.
 *
 * ⚠️ NEGA IKKI BOSQICH. Ilgari fayl tanlanishi bilan bazaga tushardi
 * va foydalanuvchi nima kirganini FAQAT KEYIN ko'rardi. Ikkita xato
 * jimgina o'tib ketardi: noto'g'ri fayl (o'tgan haftaning eksporti,
 * boshqa bo'limniki) va takroriy yuklash. Ikkalasini ham orqaga
 * qaytarish yo'q — savdolar allaqachon yozilgan bo'lardi.
 *
 * ⚠️ BEKOR QILINSA HECH QANDAY SO'ROV KETMAYDI. 2-bosqichda faqat
 * brauzerdagi `File` obyekti va hisob-kitob turadi; modal yopilsa
 * ikkalasi ham tashlanadi.
 *
 * FAYL TURI TANLANMAYDI. Uchta har xil eksport keladi (operatsiyalar
 * registri, kontragentlar katalogi, balans hisoboti) va ularni
 * backend SARLAVHA bo'yicha o'zi taniydi. Ekranda «tur» tanlagichi
 * bo'lganida u faqat xato manbai bo'lardi.
 *
 * ⚠️ IMPORT TARTIBI ERKIN. Registr katalogdan oldin yuklansa savdolar
 * telefonsiz qoladi va ro'yxat BO'SH ko'rinadi — ya'ni «hammasi
 * joyida» degan yolg'on ma'no beradi. Katalog kelganda backend
 * bog'lanishlarni tiklaydi (`linked_sales`), shuning uchun hisobotda
 * aynan shu son alohida ko'rsatiladi.
 */

import {
  CalendarRange,
  CheckCircle2,
  FileSpreadsheet,
  Info,
  TriangleAlert,
  Upload,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  useImportSales,
  usePreviewSalesImport,
  type SalesImportPreview,
  type SalesImportReport,
} from '@/modules/sales/api'
import { ApiError } from '@/shared/api/client'
import { formatFullDate } from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal } from '@/shared/ui/Modal'
import { Badge, Button, Skeleton } from '@/shared/ui/primitives'

/** Brauzer dialogida ko'rinadigan fayllar. Faqat `.xlsx`: backend
 *  `openpyxl` bilan o'qiydi va eski `.xls` ni umuman ochmaydi. */
const ACCEPT = '.xlsx'

/** Ogohlantirishlar blokida nechta mijoz kodi ko'rsatiladi.
 *
 *  Backend 20 tagacha yuboradi, ekranda esa 5 tasi yetarli: ro'yxatning
 *  vazifasi «qanaqa kodlar ekan?» degan savolga javob berish, to'liq
 *  ro'yxat bilan ishlash emas. Umumiy son yonida turadi. */
const CODE_SAMPLE = 5

/** `YYYY-MM-DD` → `12/08/2026`.
 *
 *  ⚠️ `T00:00:00` qo'shilishi MAJBURIY: `new Date('2026-08-12')` UTC
 *  yarim tunini beradi va Toshkentda (UTC+5) sana bir kun orqaga
 *  siljib ketardi. Ro'yxat sahifasi ham aynan shunday qiladi. */
const day = (iso: string) => formatFullDate(`${iso}T00:00:00`)

/** Davrdagi kunlar soni — ikkala chekka ham kiradi. */
function dayCount(from: string, to: string): number {
  const start = new Date(`${from}T00:00:00`).getTime()
  const end = new Date(`${to}T00:00:00`).getTime()
  return Math.round((end - start) / 86_400_000) + 1
}

export function ImportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const check = usePreviewSalesImport()
  const upload = useImportSales()
  const inputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<SalesImportPreview | null>(null)
  const [report, setReport] = useState<SalesImportReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const busy = check.isPending || upload.isPending

  const reset = () => {
    setFile(null)
    setPreview(null)
    setReport(null)
    setError(null)
    check.reset()
    upload.reset()
  }

  // Har ochilishda toza holat — o'tgan safargi hisobot yangi faylga
  // tegishlidek ko'rinib qolmasin
  useEffect(() => {
    if (!open) return
    reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const fail = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : t('common.error'))

  /** 1-bosqich: faylni hisoblab ko'rish. Baza tegilmaydi. */
  const runPreview = () => {
    if (!file) return
    setError(null)
    check.mutate(file, { onSuccess: setPreview, onError: fail })
  }

  /** 2-bosqich: tasdiqlangan faylning O'ZINI yozish. */
  const confirm = () => {
    if (!file) return
    setError(null)
    upload.mutate(file, { onSuccess: setReport, onError: fail })
  }

  const title = report
    ? t('sales.import.doneTitle')
    : preview
      ? t('sales.import.previewTitle')
      : t('sales.import.title')

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={title}
      description={
        report
          ? undefined
          : preview
            ? t('sales.import.previewHint')
            : t('sales.import.hint')
      }
      size="md"
      footer={
        report ? (
          <>
            {/* Uchta fayl ketma-ket yuklanadi — modalni yopib qayta
                ochish o'rniga shu yerdan davom etish mumkin */}
            <Button variant="secondary" onClick={reset}>
              {t('sales.import.another')}
            </Button>
            <Button onClick={onClose}>{t('common.close')}</Button>
          </>
        ) : preview ? (
          <>
            {/* ⚠️ «Bekor qilish» — hech qanday so'rov yubormaydi.
                Bazada bu bosqichgacha hech nima o'zgarmagan. */}
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t('common.cancel')}
            </Button>
            {/* Yangi qator bo'lmasa tugma IKKILAMCHI ko'rinishda:
                bosish mumkin (yangilanish uchun), lekin u endi
                kutilayotgan amal emas */}
            <Button
              variant={preview.new_rows > 0 ? 'primary' : 'secondary'}
              disabled={busy}
              onClick={confirm}
            >
              {upload.isPending
                ? t('sales.import.running')
                : t('sales.import.confirm')}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t('common.cancel')}
            </Button>
            <Button disabled={!file || busy} onClick={runPreview}>
              {check.isPending ? t('sales.import.checking') : t('sales.import.start')}
            </Button>
          </>
        )
      }
    >
      {report ? (
        <ImportReportView report={report} />
      ) : preview ? (
        <PreviewView preview={preview} error={error} pending={upload.isPending} />
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

          {/* «Avval ko'rasiz, keyin yoziladi» — bu va'da fayl
              tanlashdan OLDIN aytiladi, aks holda foydalanuvchi
              «Yuklash» tugmasini bosishga tortinadi */}
          <p className="rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
            {t('sales.import.twoStepNote')}
          </p>

          {check.isPending && (
            <div className="space-y-2">
              <p className="text-2xs text-muted">{t('sales.import.checkingHint')}</p>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          )}

          {error && <ErrorNote message={error} />}
        </div>
      )}
    </Modal>
  )
}

/* ── Xato ─────────────────────────────────────────────────────
   Backendning o'zbekcha xabari — u faylning NIMA ekanini ham aytadi
   («bu balans hisoboti»), shuning uchun o'zgartirilmaydi. */

function ErrorNote({ message }: { message: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex animate-scale-in items-start gap-3 rounded-2xl bg-bad/[0.08] p-3.5">
      <span className="icon-tile size-9 shrink-0 text-bad">
        <TriangleAlert className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-bad">{t('sales.import.failed')}</p>
        <p className="mt-0.5 text-2xs leading-relaxed text-muted">{message}</p>
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════
   2-BOSQICH — HISOB-KITOB

   Bu ekranning yagona vazifasi: foydalanuvchi «Tasdiqlash» tugmasini
   bosishdan OLDIN nima bo'lishini bilsin. Shuning uchun bu yerda
   taxmin yo'q — hamma son fayldan va bazadan olingan.
   ══════════════════════════════════════════════════════════════ */

function PreviewView({
  preview,
  error,
  pending,
}: {
  preview: SalesImportPreview
  error: string | null
  pending: boolean
}) {
  const { t } = useTranslation()

  /** Hammasi allaqachon bazada — bu ENG KO'P uchraydigan holat
   *  (kunlik eksportlar bir-birini qoplab ketadi) va u ochiq
   *  aytilishi kerak, aks holda foydalanuvchi «0 yangi» hisobotini
   *  nosozlik deb o'ylaydi. */
  const nothingNew = preview.new_rows === 0

  const period =
    preview.date_from && preview.date_to
      ? `${day(preview.date_from)} — ${day(preview.date_to)} · ${t(
          'sales.import.preview.dayCount',
          { count: dayCount(preview.date_from, preview.date_to) },
        )}`
      : null

  const hasWarnings =
    preview.warnings.length > 0 ||
    preview.unknown_partner_count > 0 ||
    preview.unmatched_branches.length > 0 ||
    preview.without_phone > 0

  return (
    <div className="space-y-4">
      {/* ── Fayl: turi, nomi, davri ───────────────────────── */}
      <div className="flex items-start gap-3 rounded-2xl bg-surface-2/60 p-4">
        <span className="icon-tile size-10 shrink-0 text-accent">
          <FileSpreadsheet className="size-5" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            {t(`sales.import.kind.${preview.kind}`, { defaultValue: preview.kind })}
          </p>
          <p className="mt-0.5 truncate text-2xs text-muted">{preview.filename}</p>
          {period && (
            <p className="tnum mt-1.5 flex items-center gap-1.5 text-2xs text-muted">
              <CalendarRange className="size-3.5 shrink-0" />
              {period}
            </p>
          )}
        </div>
      </div>

      {/* ── Uchta katta son ───────────────────────────────────
          ⚠️ ULAR QO'SHILMAYDI. «Jami» — fayldagi qatorlar soni,
          birinchi ikkitasi esa NOYOB kalitlar bo'yicha. Faylda bir
          operatsiya raqami ikki marta uchraydi, ya'ni farq bo'lishi
          normal va u ogohlantirishlar blokida tushuntiriladi. */}
      <div className="grid grid-cols-3 gap-2">
        <BigStat
          label={t('sales.import.preview.new')}
          value={preview.new_rows}
          tone={nothingNew ? 'muted' : 'good'}
        />
        <BigStat
          label={t('sales.import.preview.existing')}
          value={preview.existing_rows}
        />
        <BigStat label={t('sales.import.preview.total')} value={preview.rows} />
      </div>

      {nothingNew && (
        <p className="flex items-start gap-2 rounded-xl bg-surface-2/60 px-3.5 py-3 text-2xs leading-relaxed text-muted">
          <Info className="mt-px size-3.5 shrink-0" />
          {t('sales.import.preview.alreadyLoaded')}
        </p>
      )}

      {/* ── Turlar kesimi ─────────────────────────────────── */}
      {preview.by_type.length > 0 && (
        <section>
          <SectionTitle>
            {t(`sales.import.preview.byType.${preview.kind}`, {
              defaultValue: t('sales.import.preview.byType.register'),
            })}
          </SectionTitle>
          <div className="overflow-hidden rounded-2xl bg-surface-2/60">
            {preview.by_type.map((row) => (
              <div
                key={row.type}
                className="flex items-center gap-3 border-b border-border/40 px-3.5 py-2 last:border-0"
              >
                {/* Tarjimasi bo'lsa — tarjima, bo'lmasa SAP dagi so'z.
                    Katalog va balansda bu yerda guruh/bo'lim nomi
                    turadi va ular tarjima qilinmaydi. */}
                <span className="min-w-0 flex-1 truncate text-xs">
                  {t(`sales.import.opType.${row.type}`, { defaultValue: row.label })}
                </span>
                <span className="tnum shrink-0 text-xs font-semibold">
                  {formatNumber(row.count)}
                </span>
                {row.amount_usd != null && (
                  <span className="tnum w-24 shrink-0 text-right text-2xs text-muted">
                    {formatNumber(Math.round(row.amount_usd))} $
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Kunlar bo'yicha ───────────────────────────────── */}
      {preview.by_day.length > 0 && <DayChart days={preview.by_day} />}

      {/* ── Ogohlantirishlar ──────────────────────────────── */}
      {hasWarnings && <WarningBlock preview={preview} />}

      {pending && (
        <div className="space-y-2">
          <p className="text-2xs text-muted">{t('sales.import.runningHint')}</p>
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {error && <ErrorNote message={error} />}
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="mb-1.5 px-0.5 text-2xs font-medium text-muted">{children}</div>
}

function BigStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'good' | 'muted'
}) {
  return (
    <div className="rounded-2xl bg-surface-2/60 px-3.5 py-3">
      <div className="text-2xs text-muted">{label}</div>
      <div
        className={cn(
          'tnum mt-0.5 text-xl font-semibold tracking-tight',
          tone === 'good' && value > 0 && 'text-good',
          tone === 'muted' && value === 0 && 'text-muted',
        )}
      >
        {formatNumber(value)}
      </div>
    </div>
  )
}

/* ── Kunlar diagrammasi ───────────────────────────────────────
   Ustunli emas, YOTIQ zolakli: kunlar soni oldindan noma'lum
   (kunlik eksport — bir necha kun, oylik — o'ttizdan ortiq) va yotiq
   ro'yxat har qanday uzunlikda o'qilaveradi hamda aylantirilaveradi.
   Ustunli diagramma esa 30 kunda tanib bo'lmas darajada siqilardi.

   ⚠️ Zolak eng KATTA kunga nisbatan chiziladi, umumiy songa emas:
   maqsad kunlarni bir-biri bilan solishtirish. */

function DayChart({
  days,
}: {
  days: { day: string; count: number; amount_usd: number | null }[]
}) {
  const { t } = useTranslation()
  const max = useMemo(() => Math.max(...days.map((d) => d.count), 1), [days])

  return (
    <section>
      <SectionTitle>{t('sales.import.preview.byDay')}</SectionTitle>
      <div className="max-h-52 space-y-1 overflow-y-auto rounded-2xl bg-surface-2/60 p-3">
        {days.map((row) => (
          <div key={row.day} className="flex items-center gap-2.5">
            <span className="tnum w-16 shrink-0 text-2xs text-muted">
              {day(row.day)}
            </span>
            <span className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-surface">
              <span
                className="block h-full rounded-full bg-accent/70"
                style={{ width: `${Math.max((row.count / max) * 100, 2)}%` }}
              />
            </span>
            <span className="tnum w-10 shrink-0 text-right text-2xs font-medium">
              {formatNumber(row.count)}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ── Ogohlantirishlar ─────────────────────────────────────────
   Bu blok IMPORTNI TO'XTATMAYDI — u fayl bilan nima noto'g'ri
   ekanini aytadi. Har qatorning ortida aniq keyingi qadam turadi:
   katalogni yuklash, filialga xodim biriktirish. */

function WarningBlock({ preview }: { preview: SalesImportPreview }) {
  const { t } = useTranslation()

  return (
    <div className="space-y-2 rounded-2xl bg-warn/[0.08] p-3.5">
      <div className="flex items-center gap-1.5 text-2xs font-medium text-warn">
        <TriangleAlert className="size-3.5" />
        {t('sales.import.preview.warnings')}
      </div>

      {/* Backendning tayyor o'zbekcha jumlalari — ularda aniq son
          bor («3 qatorda sana o'qilmadi») va ular o'zgartirilmaydi */}
      {preview.warnings.map((text) => (
        <p key={text} className="text-2xs leading-relaxed text-muted">
          {text}
        </p>
      ))}

      {preview.without_phone > 0 && (
        <p className="text-2xs leading-relaxed text-muted">
          {t('sales.import.preview.withoutPhone', { count: preview.without_phone })}
        </p>
      )}

      {/* Kodlar SON bilan emas, NAMUNA bilan: rahbar birinchi
          kodlarni ko'rib fayl qaysi davrniki ekanini taniydi */}
      {preview.unknown_partner_count > 0 && (
        <div>
          <p className="text-2xs leading-relaxed text-muted">
            {t('sales.import.preview.unknownPartners', {
              count: preview.unknown_partner_count,
            })}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {preview.unknown_partners.slice(0, CODE_SAMPLE).map((code) => (
              <Badge key={code} tone="warn">
                {code}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Filiallar SON bilan emas, NOMLARI bilan: «7 ta filial
          biriktirilmadi» xabari bilan hech nima qilib bo'lmaydi,
          nomlar bilan esa darhol ish boshlanadi */}
      {preview.unmatched_branches.length > 0 && (
        <div>
          <p className="text-2xs leading-relaxed text-muted">
            {t('sales.import.unmatchedBranches', {
              count: preview.unmatched_branches.length,
            })}
          </p>
          <div className="mt-1.5 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
            {preview.unmatched_branches.map((branch) => (
              <Badge key={branch} tone="warn">
                {branch}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
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
