/**
 * Davr tanlash.
 *
 * Tepada to'rt bo'lim: Tayyor · Oy · Yil · Oraliq. Bir vaqtda faqat
 * bittasining ichi ko'rinadi — shuning uchun «tayyor davr bilan yilni
 * birga tanlasa bo'ladimi?» degan savol umuman tug'ilmaydi. Ilgari
 * uchalasi yonma-yon turgani chalkashlik tug'dirgan edi.
 *
 * Tanlov darhol qo'llanadi. «Oraliq» bundan mustasno: u ikkita
 * qiymatdan iborat, shuning uchun ikkala sana ham to'g'ri bo'lgandagina
 * va qisqa kechikish bilan qo'llanadi — aks holda birinchi sanani
 * o'zgartirgan zahoti keraksiz so'rov ketardi.
 */

import * as Popover from '@radix-ui/react-popover'
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  customRange,
  formatFullDate,
  isFutureMonth,
  MONTHS_UZ,
  MONTHS_UZ_SHORT,
  resolveMonth,
  resolvePreset,
  resolveYear,
  toInputValue,
  type DateRange,
  type PresetKey,
} from '@/shared/lib/date'
import { cn } from '@/shared/lib/utils'
import { Input, Label } from '@/shared/ui/primitives'

const PRESETS: { key: PresetKey; labelKey: string }[] = [
  { key: 'last7', labelKey: 'range.last7' },
  { key: 'last30', labelKey: 'range.last30' },
  { key: 'last45', labelKey: 'range.last45' },
  { key: 'last90', labelKey: 'range.last90' },
  { key: 'thisMonth', labelKey: 'range.thisMonth' },
  { key: 'lastMonth', labelKey: 'range.lastMonth' },
  { key: 'thisQuarter', labelKey: 'range.thisQuarter' },
  { key: 'thisYear', labelKey: 'range.thisYear' },
]

const FIRST_YEAR = 2023
const CURRENT_YEAR = new Date().getFullYear()
const YEARS = Array.from(
  { length: CURRENT_YEAR - FIRST_YEAR + 1 },
  (_, i) => CURRENT_YEAR - i,
)

type Tab = 'preset' | 'month' | 'year' | 'custom'

/** Davr chegaraning ICHIDA to'liq joylashadimi.
 *
 *  Qisman chiqib ketgani ham YARAMAYDI. «Oxirgi 90 kun» ning 45 kuni
 *  ishlaydi, lekin yorlig'i yolg'on gapiradi: foydalanuvchi 90 kunlik
 *  ma'lumot keldi deb o'ylab, yetishmayotganini nosozlik deb hisoblaydi.
 *  Shuning uchun mezon — boshi ham chegara ichida bo'lsin. */
function insideWindow(range: DateRange, earliest?: Date | null): boolean {
  if (!earliest) return true
  return range.from >= earliest
}

/** Boshini chegaraga tortadi.
 *
 *  Tayyor davrlar va oylar chegaradan oshsa umuman KO'RSATILMAYDI,
 *  shuning uchun bu yerga faqat «Oraliq» bo'limida qo'lda kiritilgan
 *  sana yetib keladi. Uni rad etish o'rniga qirqamiz: foydalanuvchi
 *  «1-iyundan» deb yozsa, 3-iyuldan boshlangani unga baribir kerak.
 *  Qirqilmasa backend jimgina qisqartirardi va tanlagichda boshqa
 *  sana ko'rinib turardi. */
function clampStart(range: DateRange, earliest?: Date | null): DateRange {
  if (!earliest || range.from >= earliest) return range
  // Oxiri ham chegaradan oldin bo'lsa qirqib bo'lmaydi: oraliq TESKARI
  // bo'lib qolardi va tugmada «03.07.2026 — 02.03.2026» ko'rinardi.
  // Bunday tanlov sana maydonlaridagi `min` bilan to'siladi, o'tib
  // ketsa backend tushunarli xato qaytaradi.
  if (range.to < earliest) return range
  return customRange(earliest, range.to)
}

/** Ochilganda qaysi bo'lim ko'rinishi — joriy tanlovga qarab */
function tabFor(range: DateRange): Tab {
  if (range.preset) return 'preset'
  if (range.month != null) return 'month'
  if (range.year != null) return 'year'
  return 'custom'
}

export function DateRangePicker({
  value,
  onChange,
  earliest,
}: {
  value: DateRange
  onChange: (next: DateRange) => void
  /**
   * Eng eski TANLASH MUMKIN bo'lgan kun.
   *
   * MoyZvonki sinxronizatsiyasida kerak: undan oldingi kunlarda yozuv
   * yo'q, ya'ni qancha keng oraliq tanlansa ham bitta qo'ng'iroq
   * qo'shilmaydi. Ishlamaydigan tanlovni taklif qilish — foydalanuvchini
   * bejiz urinishga yuborish.
   *
   * Chegarani backend beradi (`GET /calls/sync/window`) va so'rovni
   * o'zi ham shu bilan qisqartiradi — ya'ni bu prop yagona to'siq
   * emas, faqat tanlovni haqiqatga moslaydi. Berilmasa — cheklov yo'q.
   */
  earliest?: Date | null
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>(() => tabFor(value))

  // «Oy» bo'limida ko'rilayotgan yil — tanlangandan alohida
  const [browseYear, setBrowseYear] = useState(() => value.year ?? CURRENT_YEAR)

  const [from, setFrom] = useState(() => toInputValue(value.from))
  const [to, setTo] = useState(() => toInputValue(value.to))

  const label = value.preset
    ? t(`range.${value.preset}`)
    : value.month != null && value.year != null
      ? `${MONTHS_UZ[value.month]} ${value.year}`
      : value.year != null
        ? `${value.year}`
        : `${formatFullDate(value.from)} — ${formatFullDate(value.to)}`

  // Oyna ochilganda joriy tanlovga mos bo'limni ko'rsatamiz
  const openChange = (next: boolean) => {
    if (next) {
      setTab(tabFor(value))
      setBrowseYear(value.year ?? CURRENT_YEAR)
      setFrom(toInputValue(value.from))
      setTo(toInputValue(value.to))
      /* Oyna ochilganda ham yangilanadi: aks holda shunchaki ochib
         yopish ham keraksiz so'rov yuborardi */
      applied.current = `${toInputValue(value.from)}|${toInputValue(value.to)}`
    }
    setOpen(next)
  }

  // Tanlov to'liq — qo'llab, oynani yopamiz
  const pick = (next: DateRange) => {
    onChange(clampStart(next, earliest))
    setOpen(false)
  }

  /* Chegaradan oshadigan tanlovlar ro'yxatdan CHIQARILADI, o'chirilgan
     holda qoldirilmaydi. O'chirilgan tugma «bu bor, lekin hozir
     ishlamayapti» degan ma'no beradi va foydalanuvchi sababini qidiradi;
     aslida u umuman ishlamaydi. */
  const presets = PRESETS.filter((item) =>
    insideWindow(resolvePreset(item.key), earliest),
  )
  const years = YEARS.filter((year) => insideWindow(resolveYear(year), earliest))

  const TABS: { key: Tab; labelKey: string }[] = [
    { key: 'preset', labelKey: 'range.tabPreset' },
    { key: 'month', labelKey: 'range.tabMonth' },
    // Butun yil 45 kunga sig'maydi — chegara bo'lsa bo'lim keraksiz
    ...(years.length ? [{ key: 'year' as Tab, labelKey: 'range.tabYear' }] : []),
    { key: 'custom', labelKey: 'range.tabCustom' },
  ]

  /* Tanlangan bo'lim ro'yxatdan chiqib ketishi mumkin: chegara
     endpointdan KECHROQ keladi, ya'ni «Yil» ochiq turganda bo'lim
     yo'qolishi mumkin. O'shanda oyna bo'sh ko'rinardi. */
  const activeTab = TABS.some((item) => item.key === tab) ? tab : 'preset'

  /* Oraliq: ikkala sana to'g'ri bo'lgandagina qo'llanadi. Kechikish —
     foydalanuvchi ikkinchi sanani tanlashga ulgursin uchun.

     `onChange` ref'da saqlanadi: ota-komponent uni inline funksiya
     sifatida uzatsa, har renderda yangi bo'lib chiqadi va taymer
     qayta-qayta tiklanib hech qachon ishlamay qolardi. */
  /* ⚠️ JORIY QIYMAT bilan boshlanadi, bo'sh satr bilan EMAS.
     Bo'sh bo'lsa birinchi renderdayoq «o'zgardi» deb hisoblanib,
     500 ms dan keyin `onChange` bejiz chaqirilardi. Natijada
     foydalanuvchi hech narsaga tegmagan bo'lsa ham butun sahifa
     qaytadan yuklanardi: kartalar, grafik va jadval yana skeletonga
     aylanardi va analitika so'rovi ikki marta ketardi.
     Faqat boshlang'ich davri «Oraliq» bo'lgan sahifalarda ko'rinardi —
     Faollik bo'limi aynan shunday. */
  const applied = useRef(`${toInputValue(value.from)}|${toInputValue(value.to)}`)
  const latestChange = useRef(onChange)
  latestChange.current = onChange
  // `earliest` — har renderda yangi `Date` obyekti bo'lishi mumkin,
  // shuning uchun effekt bog'liqligiga qo'shilmaydi (aks holda taymer
  // uzluksiz tiklanardi)
  const earliestRef = useRef(earliest)
  earliestRef.current = earliest

  useEffect(() => {
    if (activeTab !== 'custom') return
    const f = new Date(from)
    const tt = new Date(to)
    if (Number.isNaN(f.getTime()) || Number.isNaN(tt.getTime())) return
    if (f > tt) return

    const key = `${from}|${to}`
    if (key === applied.current) return

    const timer = setTimeout(() => {
      applied.current = key
      latestChange.current(clampStart(customRange(f, tt), earliestRef.current))
    }, 500)
    return () => clearTimeout(timer)
  }, [activeTab, from, to])

  return (
    <Popover.Root open={open} onOpenChange={openChange}>
      <Popover.Trigger asChild>
        <button
          className={cn(
            'inline-flex h-9 items-center gap-2 rounded-xl bg-surface-2 px-3.5 text-xs font-medium',
            'transition-all duration-250 ease-ios active:scale-[0.97]',
            'hover:bg-surface-2/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
          )}
        >
          <CalendarDays className="size-3.5 text-muted" />
          <span className="tnum">{label}</span>
          <ChevronDown className="size-3.5 text-muted" />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className={cn(
            'z-50 w-[320px] max-w-[calc(100vw-2rem)] rounded-2xl bg-surface p-3 shadow-pop',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
          )}
        >
          {/* Bo'limlar — bir vaqtda faqat bittasi ochiq */}
          <div className="mb-3 flex gap-0.5 rounded-xl bg-surface-2 p-0.5">
            {TABS.map((item) => (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={cn(
                  'flex-1 rounded-[10px] px-2 py-1.5 text-2xs font-medium',
                  'transition-all duration-250 ease-ios',
                  activeTab === item.key
                    ? 'bg-surface text-text shadow-xs'
                    : 'text-muted hover:text-text',
                )}
              >
                {t(item.labelKey)}
              </button>
            ))}
          </div>

          {/* ── Tayyor davrlar ── */}
          {activeTab === 'preset' && (
            <div className="flex flex-col gap-0.5">
              {presets.map((preset) => (
                <button
                  key={preset.key}
                  onClick={() => pick(resolvePreset(preset.key))}
                  className={cn(
                    'rounded-lg px-3 py-2 text-left text-xs',
                    'transition-colors duration-250 ease-ios',
                    value.preset === preset.key
                      ? 'bg-accent-soft font-medium text-accent'
                      : 'text-muted hover:bg-surface-2 hover:text-text',
                  )}
                >
                  {t(preset.labelKey)}
                </button>
              ))}
            </div>
          )}

          {/* ── Oy: yil + oy ── */}
          {activeTab === 'month' && (
            <div>
              <div className="mb-2.5 flex items-center justify-between">
                <button
                  onClick={() => setBrowseYear((y) => Math.max(FIRST_YEAR, y - 1))}
                  disabled={browseYear <= FIRST_YEAR}
                  className="grid size-7 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text disabled:opacity-30"
                  aria-label={t('range.prevYear')}
                >
                  <ChevronLeft className="size-4" />
                </button>
                <span className="tnum text-sm font-semibold">{browseYear}</span>
                <button
                  onClick={() => setBrowseYear((y) => Math.min(CURRENT_YEAR, y + 1))}
                  disabled={browseYear >= CURRENT_YEAR}
                  className="grid size-7 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text disabled:opacity-30"
                  aria-label={t('range.nextYear')}
                >
                  <ChevronRight className="size-4" />
                </button>
              </div>

              <div className="grid grid-cols-4 gap-1">
                {MONTHS_UZ_SHORT.map((name, index) => {
                  const future =
                    isFutureMonth(browseYear, index) ||
                    !insideWindow(resolveMonth(browseYear, index), earliest)
                  const active = value.year === browseYear && value.month === index
                  return (
                    <button
                      key={name}
                      disabled={future}
                      onClick={() => pick(resolveMonth(browseYear, index))}
                      className={cn(
                        'rounded-lg py-2 text-2xs font-medium capitalize',
                        'transition-all duration-250 ease-ios active:scale-95',
                        'disabled:cursor-not-allowed disabled:opacity-25',
                        active
                          ? 'bg-accent text-white'
                          : 'text-muted hover:bg-surface-2 hover:text-text',
                      )}
                    >
                      {name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* ── Yil ── */}
          {activeTab === 'year' && (
            <div className="flex flex-col gap-0.5">
              {years.map((year) => (
                <button
                  key={year}
                  onClick={() => pick(resolveYear(year))}
                  className={cn(
                    'tnum rounded-lg px-3 py-2 text-left text-xs',
                    'transition-colors duration-250 ease-ios',
                    value.year === year && value.month == null
                      ? 'bg-accent-soft font-medium text-accent'
                      : 'text-muted hover:bg-surface-2 hover:text-text',
                  )}
                >
                  {year}
                </button>
              ))}
            </div>
          )}

          {/* ── Ixtiyoriy oraliq ── */}
          {activeTab === 'custom' && (
            <div className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="mb-1">{t('range.from')}</Label>
                  <Input
                    type="date"
                    className="h-9 text-xs"
                    value={from}
                    min={earliest ? toInputValue(earliest) : undefined}
                    max={to}
                    onChange={(e) => setFrom(e.target.value)}
                  />
                </div>
                <div>
                  <Label className="mb-1">{t('range.to')}</Label>
                  <Input
                    type="date"
                    className="h-9 text-xs"
                    value={to}
                    min={earliest ? toInputValue(earliest) : from}
                    max={toInputValue(new Date())}
                    onChange={(e) => setTo(e.target.value)}
                  />
                </div>
              </div>
              <p className="text-2xs text-muted">{t('range.customHint')}</p>
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
