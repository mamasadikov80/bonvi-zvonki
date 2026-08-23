/**
 * Filtrlar paneli.
 *
 * Hudud va xodim — DROPDOWN ichida (`MultiSelect`). Ilgari hududlar
 * ekranga uzun tugmalar qatori bo'lib yoyilardi va admin yangi hudud
 * qo'shgan sari panel o'sib borardi; xodim filtri esa `<select>` ichiga
 * `✓` belgisini yopishtirgan vaqtinchalik yechim edi.
 *
 * Til filtri OLIB TASHLANDI: qo'ng'iroq yozuvlarining deyarli hammasi
 * o'zbek/rus aralash, ya'ni filtr hech narsani ajratmasdi va panelda
 * shovqin bo'lib turardi. Endi u tag-tugi bilan yo'q — `calls.language`
 * ustuni ham, `AnalyticsQuery.languages` maydoni ham.
 *
 * Hududlar ro'yxati `GET /regions` dan olinadi, `/analytics/filters`
 * dan emas: admin yangi hudud qo'shsa, u hali hech kimga
 * biriktirilmagan bo'lsa ham filtrda turishi kerak.
 */

import { MapPin, RotateCcw, SlidersHorizontal, User } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { AnalyticsQuery } from '@/modules/analytics/api'
import { useFilterOptions } from '@/modules/analytics/api'
import { sortRegions, useRegions } from '@/modules/regions/api'
import { rangeToQuery, type DateRange } from '@/shared/lib/date'
import { DateRangePicker } from '@/shared/ui/DateRangePicker'
import { MultiSelect, type MultiSelectOption } from '@/shared/ui/MultiSelect'
import { Button } from '@/shared/ui/primitives'

interface Props {
  value: AnalyticsQuery
  onChange: (next: AnalyticsQuery) => void
  range: DateRange
  onRangeChange: (next: DateRange) => void
  /** SALES roli uchun xodim filtri yashiriladi */
  showAgentFilter?: boolean
  /**
   * SALES roli uchun hudud filtri ham yashiriladi.
   *
   * Sabab texnik: bu sahifadagi qo'ng'iroqlar analitikasi hududni
   * `agents.region` bo'yicha filtrlaydi. Savdo xodimining BARCHA
   * qo'ng'iroqlari bitta xodimga, demak bitta hududga tegishli —
   * ya'ni tanlov yo hammasini qoldiradi, yo hammasini yo'qotadi.
   * Ishlamaydigan filtrni ko'rsatgandan ko'ra ko'rsatmagan yaxshi.
   *
   * Hudud kesimi «Mening baholarim» sahifasida MA'NOLI: u yerda
   * hudud guruhdan olinadi va bitta xodim bir nechta hududdagi
   * guruhlarga xizmat ko'rsatishi mumkin.
   */
  showRegionFilter?: boolean
  /**
   * Sahifaga XOS filtrlar — umumiylaridan keyin, o'sha qatorda.
   *
   * Mijozlar sahifasida qidiruv va «kim ro'yxatga kiradi» tanlovi bor;
   * ular alohida kartada turganda ekranda ikkita bir xil ko'rinishdagi
   * qator hosil bo'lardi va jadval pastga surilardi. Bu yerda ular
   * bitta qatorga qo'shiladi.
   *
   * Bermagan sahifalar (Boshqaruv paneli, Faollik) uchun hech narsa
   * o'zgarmaydi — `undefined` hech qanday tugun chizmaydi.
   *
   * ⚠️ To'g'ridan-to'g'ri chiziladi (o'rovchi `div` YO'Q), ya'ni
   * berilgan element flex qatorining bevosita bolasi bo'ladi va
   * `flex-1` kabi sinflar ishlaydi.
   */
  children?: ReactNode
}

/** Bo'sh ro'yxat filtr emas — so'rovga `regions=[]` yuborilmaydi */
const orUndefined = (list: string[]): string[] | undefined =>
  list.length ? list : undefined

export function FilterBar({
  value,
  onChange,
  range,
  onRangeChange,
  showAgentFilter = true,
  showRegionFilter = true,
  children,
}: Props) {
  const { t } = useTranslation()
  const { data: options } = useFilterOptions()

  /* Hududlar — faolsizlar ham keladi: tarixiy qo'ng'iroqlar
     faolsizlantirilgan hudud ostida qolgan bo'lishi mumkin, ularni
     filtrlash imkoni yo'qolmasin. Faol emasligi ro'yxatda aytiladi. */
  const { data: regions } = useRegions(true)

  const regionOptions = useMemo<MultiSelectOption[]>(() => {
    const rows = sortRegions(regions ?? [])
    const list = [...rows.filter((r) => r.is_active), ...rows.filter((r) => !r.is_active)]
    const known = new Set(list.map((r) => r.name))
    // Tanlangan, lekin ro'yxatdan chiqib ketgan qiymat yo'qolmasin
    const orphans = (value.regions ?? []).filter((name) => !known.has(name))
    return [
      ...list.map((region) => ({
        value: region.name,
        label: region.name,
        hint: region.is_active ? undefined : t('regions.inactive'),
      })),
      ...orphans.map((name) => ({ value: name, label: name })),
    ]
  }, [regions, value.regions, t])

  const agentOptions = useMemo<MultiSelectOption[]>(
    () =>
      (options?.agents ?? []).map((agent) => ({
        value: agent.id,
        label: agent.name,
        hint: agent.region || undefined,
      })),
    [options?.agents],
  )

  const hasFilters = Boolean(value.agent_ids?.length || value.regions?.length)

  return (
    <div className="card animate-fade-up p-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-2 text-muted">
          <SlidersHorizontal className="size-4" />
          <span className="label-eyebrow">{t('filters.title')}</span>
        </div>

        {/* Davr — tayyor variantlar, yil yoki ixtiyoriy oraliq */}
        <DateRangePicker
          value={range}
          onChange={(next) => {
            onRangeChange(next)
            onChange({ ...value, days: undefined, ...rangeToQuery(next) })
          }}
        />

        {/* Hudud — dropdown, ro'yxat 8 tadan oshsa qidiruv bilan.
            BITTA variant qolganda ko'rsatilmaydi: tanlash ham,
            tanlamaslik ham bir xil natija beradi, ya'ni filtr emas —
            shunchaki bosiladigan, hech narsa o'zgartirmaydigan tugma.
            Savdo xodimida aynan shu holat: unga faqat o'zi ishlaydigan
            hududlar keladi va ko'pincha ular bitta bo'ladi. */}
        {showRegionFilter && regionOptions.length > 1 && (
          <MultiSelect
            icon={MapPin}
            label={t('filters.regions')}
            options={regionOptions}
            value={value.regions ?? []}
            onChange={(next) => onChange({ ...value, regions: orUndefined(next) })}
            summary={(count) => t('filters.regionCount', { count })}
          />
        )}

        {/* Xodim — dropdown */}
        {showAgentFilter && agentOptions.length > 0 && (
          <MultiSelect
            icon={User}
            label={t('filters.agents')}
            options={agentOptions}
            value={value.agent_ids ?? []}
            onChange={(next) => onChange({ ...value, agent_ids: orUndefined(next) })}
            summary={(count) => t('filters.agentCount', { count })}
          />
        )}

        {children}

        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => onChange({ ...rangeToQuery(range) })}
          >
            <RotateCcw className="size-3.5" />
            {t('filters.reset')}
          </Button>
        )}
      </div>
    </div>
  )
}
