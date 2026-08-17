/**
 * Telegram Mini App qatlami.
 *
 * `telegram-web-app.js` `index.html` da ulanadi va `window.Telegram.WebApp`
 * ni yaratadi. Skript faqat Telegram ichida ma'noli ishlaydi — oddiy
 * brauzerda `initData` bo'sh qaytadi.
 *
 * Bu fayl uch ishni bajaradi:
 *   1. SDK ni xavfsiz o'qiydi (yo'q bo'lsa `null`, xato emas)
 *   2. `ready()` / `expand()` ni chaqiradi
 *   3. `themeParams` ni CSS o'zgaruvchilariga o'giradi
 *
 * Bu yerda hech qanday tarmoq so'rovi yo'q — `api.ts` ga qarang.
 */

import { useEffect, useState } from 'react'

/* ── SDK tiplari ─────────────────────────────────────────────
   Rasmiy `@twa-dev/types` paketi qo'shilmadi: sahifaga kerak
   bo'lgan maydonlar sanoqli, qolgani ortiqcha bog'liqlik. */

export interface TelegramThemeParams {
  bg_color?: string
  secondary_bg_color?: string
  section_bg_color?: string
  section_separator_color?: string
  text_color?: string
  hint_color?: string
  subtitle_text_color?: string
  link_color?: string
  button_color?: string
  button_text_color?: string
  accent_text_color?: string
  destructive_text_color?: string
}

export interface TelegramWebApp {
  /** Bot tokeni bilan IMZOLANGAN xom matn. Backend imzoni tekshiradi. */
  initData: string
  colorScheme: 'light' | 'dark'
  themeParams: TelegramThemeParams
  version: string
  platform: string
  isExpanded: boolean
  ready: () => void
  expand: () => void
  close: () => void
  onEvent: (event: string, handler: () => void) => void
  offEvent: (event: string, handler: () => void) => void
  setBackgroundColor?: (color: string) => void
  setHeaderColor?: (color: string) => void
  disableVerticalSwipes?: () => void
  HapticFeedback?: {
    impactOccurred?: (style: 'light' | 'medium' | 'heavy') => void
    notificationOccurred?: (type: 'error' | 'success' | 'warning') => void
    selectionChanged?: () => void
  }
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

/** SDK ni oladi. Telegram tashqarisida — `null`, hech qachon xato tashlamaydi. */
export function getWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null
  const app = window.Telegram?.WebApp
  // `initData` maydoni bo'lmasa bu bizga kerakli SDK emas
  return app && typeof app.initData === 'string' ? app : null
}

/** Yengil tebranish — bor bo'lsa. Yo'qligi xato emas. */
export function haptic(kind: 'select' | 'success' | 'error') {
  const fb = getWebApp()?.HapticFeedback
  if (!fb) return
  try {
    if (kind === 'select') fb.selectionChanged?.()
    else fb.notificationOccurred?.(kind)
  } catch {
    /* eski mijozda metod yo'q — jim o'tamiz */
  }
}

/* ── Mavzu → CSS o'zgaruvchilari ─────────────────────────────

   Sahifa Telegram ichida ochiladi va foydalanuvchining O'Z mavzusi
   bilan bir xil ko'rinishi kerak. Aks holda u reklama iframe'iga
   o'xshaydi va darhol yopiladi.

   Telegram ranglarni `#rrggbb` ko'rinishida beradi. Shaffoflik kerak
   bo'lgan joylar uchun («tanlangan» fon, ajratuvchi chiziq) har bir
   rangning RGB uchligi ham saqlanadi: `rgb(var(--sv-accent-rgb) / .12)`.

   Telegram rang bermasa (brauzer, eski mijoz) — `colorScheme` ga
   qarab zaxira palitra ishlatiladi, sahifa baribir to'g'ri ko'rinadi. */

const FALLBACK_LIGHT: Required<
  Pick<
    TelegramThemeParams,
    | 'bg_color'
    | 'secondary_bg_color'
    | 'text_color'
    | 'hint_color'
    | 'link_color'
    | 'button_color'
    | 'button_text_color'
    | 'destructive_text_color'
  >
> = {
  bg_color: '#ffffff',
  secondary_bg_color: '#f2f2f7',
  text_color: '#000000',
  hint_color: '#8e8e93',
  link_color: '#1d4e79',
  button_color: '#1d4e79',
  button_text_color: '#ffffff',
  destructive_text_color: '#e0393e',
}

/** `#RGB` yoki `#RRGGBB` → `"29 78 121"`. Noto'g'ri qiymatda `null`. */
export function hexToRgbTriplet(hex: string | undefined): string | null {
  if (!hex) return null
  const clean = hex.trim().replace(/^#/, '')
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null
  const n = parseInt(full, 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

export type ThemeVars = Record<string, string>

/**
 * `themeParams` dan sahifa ishlatadigan o'zgaruvchilar to'plami.
 *
 * Telegram bermagan maydonlar zaxiradan yoki mavjud rangdan olinadi:
 * masalan `section_bg_color` yo'q bo'lsa karta foni `bg_color` ga
 * tushadi — ikkalasi bir xil bo'lsa kartani soya ajratadi.
 */
export function themeToCssVars(
  _params: TelegramThemeParams | undefined,
  _scheme: 'light' | 'dark',
): ThemeVars {
  /* Sahifa DOIM yorug' — Telegram mavzusi e'tiborga olinmaydi.
   *
   * Ilgari `themeParams` dan rang olinardi va qorong'i mavzudagi
   * foydalanuvchi to'q ko'k sahifani ko'rardi. Foydalanuvchi qarori:
   * fon dashboarddagi kabi oq bo'lsin, to'q ko'k "bo'g'ib qo'yadi".
   *
   * Qiymatlar `index.css` dagi yorug' palitradan aynan olingan, shuning
   * uchun so'rovnoma sahifasi va panel bir xil ko'rinadi. Bu ataylab
   * bitta mavzuga bog'langan dizayn: har bir rang ochiq yozilgan,
   * shuning uchun Telegram qanday fon bersa ham sahifa o'zgarmaydi.
   */
  const LIGHT = {
    bg: '#f8fafc',
    surface: '#ffffff',
    surface2: '#f4f6f9',
    text: '#151d28',
    hint: '#677383',
    accent: '#215a8c',
    accentText: '#ffffff',
    danger: '#e74057',
    separator: '#e3e7ed',
  }

  const bg = LIGHT.bg
  const secondary = LIGHT.surface2
  const surface = LIGHT.surface
  const text = LIGHT.text
  const hint = LIGHT.hint
  const accent = LIGHT.accent
  const accentText = LIGHT.accentText
  const danger = LIGHT.danger
  const separator = LIGHT.separator
  const fb = FALLBACK_LIGHT

  const vars: ThemeVars = {
    '--sv-bg': bg,
    '--sv-surface': surface,
    '--sv-surface-2': secondary,
    '--sv-text': text,
    '--sv-hint': hint,
    '--sv-accent': accent,
    '--sv-accent-text': accentText,
    '--sv-danger': danger,
    '--sv-separator': separator,
  }

  /* Shaffoflik uchun RGB uchliklari.
     Uchlik DOIM yoziladi: `rgb(var(--sv-accent-rgb) / .12)` da o'zgaruvchi
     bo'sh qolsa butun qoida yaroqsiz bo'ladi va element rangsiz chiqadi.
     Shuning uchun Telegram rangi tushunarsiz formatda bo'lsa zaxira
     palitradan olinadi. */
  const triplets: Array<[string, string, string]> = [
    ['--sv-text-rgb', text, fb.text_color],
    ['--sv-hint-rgb', hint, fb.hint_color],
    ['--sv-accent-rgb', accent, fb.button_color],
    ['--sv-danger-rgb', danger, fb.destructive_text_color],
    ['--sv-separator-rgb', separator, fb.hint_color],
  ]
  for (const [name, value, fallback] of triplets) {
    vars[name] = hexToRgbTriplet(value) ?? hexToRgbTriplet(fallback) ?? '142 142 147'
  }

  return vars
}

export interface TelegramState {
  /** SDK topildimi (ya'ni sahifa Telegram ichida ochildimi) */
  available: boolean
  /** Imzolangan xom matn. Bo'sh bo'lsa backend hech narsa qabul qilmaydi. */
  initData: string
  colorScheme: 'light' | 'dark'
  vars: ThemeVars
}

/** Brauzerda ochilganda ham sahifa ko'rinarli bo'lishi uchun */
function browserScheme(): 'light' | 'dark' {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function snapshot(): TelegramState {
  const app = getWebApp()
  if (!app) {
    const scheme = browserScheme()
    return {
      available: false,
      initData: '',
      colorScheme: scheme,
      vars: themeToCssVars(undefined, scheme),
    }
  }
  const scheme = app.colorScheme === 'dark' ? 'dark' : 'light'
  return {
    available: true,
    initData: app.initData ?? '',
    colorScheme: scheme,
    vars: themeToCssVars(app.themeParams, scheme),
  }
}

/**
 * SDK ni ishga tushiradi va mavzuni kuzatadi.
 *
 * `ready()` — Telegram'ga «sahifa yuklandi» deydi (yuklash indikatori
 * olinadi), `expand()` — varaqni to'liq balandlikka ochadi, aks holda
 * forma yarim ekranda qoladi va odam skroll qilishi kerak bo'ladi.
 */
export function useTelegram(): TelegramState {
  const [state, setState] = useState<TelegramState>(snapshot)

  useEffect(() => {
    const app = getWebApp()
    if (!app) return

    try {
      app.ready()
      app.expand()
      // Sahifa doim yorug', shuning uchun Telegramning ustki/ostki
      // chekkalari ham yorug' bo'lishi kerak — aks holda oq sahifa
      // to'q ko'k ramka ichida qolib, ayni shu narsa "bo'g'ib"
      // ko'rsatardi.
      app.setBackgroundColor?.('#f8fafc')
      app.setHeaderColor?.('#f8fafc')
    } catch {
      /* eski mijozda ba'zi metodlar yo'q — sahifa baribir ishlaydi */
    }

    const onThemeChanged = () => setState(snapshot())
    app.onEvent('themeChanged', onThemeChanged)
    // Ba'zi mijozlar `initData` ni skript yuklangandan keyin to'ldiradi
    setState(snapshot())

    return () => app.offEvent('themeChanged', onThemeChanged)
  }, [])

  // Fon va `color-scheme` hujjat darajasida — overscroll oq chiziq bermasin
  useEffect(() => {
    const bg = state.vars['--sv-bg']
    const prevBg = document.body.style.backgroundColor
    const prevScheme = document.documentElement.style.colorScheme
    if (bg) document.body.style.backgroundColor = bg
    // Sahifa bitta mavzuga bog'langan — brauzer forma
    // elementlarini qorong'i qilib chizmasin
    document.documentElement.style.colorScheme = 'light'
    return () => {
      document.body.style.backgroundColor = prevBg
      document.documentElement.style.colorScheme = prevScheme
    }
  }, [state.vars])

  return state
}
