/**
 * «Nega shubhali» — bitta jumla.
 *
 * ⚠️ NEGA KERAK. Jadvalda `R1`/`R2`/`R3` kodlari turardi va ular
 * O'ZI HECH NIMANI tushuntirmaydi: kodni bilgan odam ham «qaysi
 * savdolar orasida suhbat yo'q?» deb qatorni ochib ko'rishga majbur
 * edi. Bu ekranni kompaniya direktori ham ochadi va u har ustunni
 * o'qishga vaqt sarflamaydi — demak MA'NONI jumla tashishi kerak,
 * yorliq emas. Yorliqlar yo'qolmaydi: ular jumla yonida kichik
 * bo'lib qoladi (tahlil qiluvchi uchun).
 *
 * ⚠️ JUMLA DALILDAN YIG'ILADI, o'ylab topilmaydi: sana, kunlar soni
 * va oldingi savdo — hammasi javobdagi maydonlar. Ya'ni rahbar
 * jumlani o'qib, o'sha zahoti uni SAP da tekshirishi mumkin
 * (shartnoma, 4-bo'lim).
 *
 * ⚠️ TARTIB — KUCHLISIDAN: R3 → R1 → R2. Bir qatorda bir nechta
 * qoida buzilgan bo'lishi mumkin, lekin jumla BITTA: «hech qachon
 * gaplashilmagan» degan fakt yonida «savdodan oldin suhbat yo'q»
 * ortiqcha gap.
 */

import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'

import type { SaleRule, SaleSkipReason, SaleVerdict } from '@/modules/sales/api'
import { formatFullDate } from '@/shared/lib/date'

/**
 * Jumla uchun yetarli faktlar.
 *
 * ⚠️ Ataylab `ComplianceRow` EMAS: aynan shu maydonlar mijoz
 * kartochkasidagi `ClientSale` da ham bor va ikkala ekran bitta
 * jumlani ko'rsatishi shart. Ikki xil matn — ikki xil haqiqat.
 */
export interface SaleFacts {
  /** `YYYY-MM-DD` — vaqtsiz */
  occurred_on: string
  verdict: SaleVerdict
  broken_rules: SaleRule[]
  skip_reason: SaleSkipReason | null
  last_call_at: string | null
  last_call_agent: string | null
  days_before: number | null
  previous_sale_on: string | null
}

/**
 * Jumlani tuzuvchi.
 *
 * `windowDays` javobdan keladi (`sales.window_days`) — sozlama
 * o'zgarsa jumla ham o'zi o'zgaradi. Frontendga ko'chirib yozilgan
 * son ikkinchi haqiqat tug'dirardi.
 */
export function useSaleReason(windowDays?: number) {
  const { t } = useTranslation()

  return useCallback(
    (sale: SaleFacts): string => {
      /* Tekshirib bo'lmadi — sabab SAP dagi ma'lumotda, savdoda emas.
         Bu «toza» degani EMAS va jumla ham shuni aytadi. */
      if (sale.verdict === 'not_checkable') {
        if (sale.skip_reason === 'generic_code') return t('sales.why.genericCode')
        if (sale.skip_reason === 'no_phone') return t('sales.why.noPhone')
        return t('sales.verdictHint.not_checkable')
      }

      const rules = sale.broken_rules

      // R3 — eng kuchlisi: butun tarixda birorta suhbat yo'q
      if (rules.includes('R3')) return t('sales.why.never')

      // R1 — savdo oldidagi oynada suhbat yo'q. Suhbatning O'ZI
      // bo'lgan bo'lsa (lekin oynadan tashqarida) — sanasi bilan
      // aytiladi: aynan shu son rahbarning savoliga javob beradi.
      if (rules.includes('R1')) {
        return sale.last_call_at
          ? t('sales.why.noCallBefore', {
              count: sale.days_before ?? 0,
              date: formatFullDate(sale.last_call_at),
            })
          : t('sales.why.noCallWindow', { count: windowDays ?? 0 })
      }

      // R2 — ikki savdo orasida suhbat yo'q. Ikkala sana ham
      // yoziladi, aks holda «qaysi ikkitasi?» degan savol qoladi.
      if (rules.includes('R2')) {
        return sale.previous_sale_on
          ? t('sales.why.betweenSales', {
              from: formatFullDate(`${sale.previous_sale_on}T00:00:00`),
              to: formatFullDate(`${sale.occurred_on}T00:00:00`),
            })
          : t('sales.rule.R2')
      }

      /* Toza. Bu ham jumla bilan aytiladi: bo'sh katak «tekshirilmadi»
         deb o'qilardi, holbuki bu yerda aniq dalil bor. */
      if (sale.last_call_at) {
        const date = formatFullDate(sale.last_call_at)
        return sale.last_call_agent
          ? t('sales.why.ok', { date, agent: sale.last_call_agent })
          : t('sales.why.okShort', { date })
      }

      return t('sales.verdictHint.ok')
    },
    [t, windowDays],
  )
}
