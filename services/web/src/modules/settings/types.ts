/**
 * Sozlamalar sahifasining umumiy turlari.
 *
 * Forma backend reyestridan (`SETTINGS_REGISTRY`) quriladi: backendga
 * bitta qator qo'shilsa, UI da yangi maydon o'zidan paydo bo'ladi.
 */

export interface SettingField {
  key: string
  label: string
  type: 'string' | 'secret' | 'number' | 'boolean' | 'select'
  options: { value: string; label: string }[]
  hint: string | null
  value: unknown
  /** Maxfiy qiymat API dan qaytmaydi — faqat shu bayroq */
  is_set: boolean
  source: 'database' | 'env' | 'default'
}

export interface SettingGroup {
  category: string
  label: string
  fields: SettingField[]
}

export interface Integration {
  id: string
  label: string
  configured: boolean
  detail: string
}

/* ── O'zgarish aniqlash ──────────────────────────────────────
   Maydonga tegilgani yetarli emas: foydalanuvchi yozib, keyin asl
   qiymatini qaytarsa, saqlash tugmasi yana o'chishi kerak. Shuning
   uchun har doim asl qiymat bilan solishtiriladi. */

export function isFieldDirty(field: SettingField, draftValue: unknown): boolean {
  if (draftValue === undefined) return false

  // Maxfiy qiymat API dan hech qachon qaytmaydi (••••••••), shuning
  // uchun solishtiradigan asl qiymat yo'q — bo'sh bo'lmasa o'zgargan
  if (field.type === 'secret') return String(draftValue ?? '').length > 0

  if (field.type === 'boolean') return Boolean(draftValue) !== Boolean(field.value)
  if (field.type === 'number') {
    return Number(draftValue ?? 0) !== Number(field.value ?? 0)
  }
  return String(draftValue ?? '') !== String(field.value ?? '')
}

/** Guruhdan bitta maydonni topadi */
export const fieldOf = (group: SettingGroup, key: string): SettingField | undefined =>
  group.fields.find((field) => field.key === key)
