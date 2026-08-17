import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import ru from './locales/ru.json'
import uz from './locales/uz.json'

export const LANGUAGES = [
  { code: 'uz', label: "O'zbekcha", short: 'UZ' },
  { code: 'ru', label: 'Русский', short: 'RU' },
  { code: 'en', label: 'English', short: 'EN' },
] as const

export type LanguageCode = (typeof LANGUAGES)[number]['code']

const STORAGE_KEY = 'zvonki-lang'

function detectLanguage(): LanguageCode {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && LANGUAGES.some((l) => l.code === stored)) {
    return stored as LanguageCode
  }
  const browser = navigator.language.slice(0, 2)
  return LANGUAGES.some((l) => l.code === browser) ? (browser as LanguageCode) : 'uz'
}

i18n.use(initReactI18next).init({
  resources: {
    uz: { translation: uz },
    ru: { translation: ru },
    en: { translation: en },
  },
  lng: detectLanguage(),
  fallbackLng: 'uz',
  interpolation: { escapeValue: false },
})

export function setLanguage(code: LanguageCode) {
  localStorage.setItem(STORAGE_KEY, code)
  i18n.changeLanguage(code)
  document.documentElement.lang = code
}

export default i18n
