/**
 * ESLint (flat config, v9).
 *
 * NEGA BU FAYL KERAK BO'LDI. Paketlar (`eslint`, `typescript-eslint`,
 * `eslint-plugin-react-hooks`) allaqachon o'rnatilgan edi va
 * `npm run lint` skripti ham bor edi — lekin CONFIG fayli yo'qligi
 * uchun buyruq har safar «couldn't find eslint.config.js» bilan
 * to'xtardi. Ya'ni tekshiruv bor deb o'ylanardi, amalda esa hech
 * qachon ishlamagan.
 *
 * Buning narxi aniq: `CallDetailPage` da `useEffect` erta `return`
 * dan KEYIN qolib ketdi. TypeScript buni ko'rmaydi (turlari to'g'ri),
 * lekin React birinchi renderda 10 ta, ikkinchisida 11 ta hook ko'rib
 * butun sahifani yiqitadi — oq ekran. `react-hooks/rules-of-hooks`
 * aynan shuni tutadi.
 *
 * Shuning uchun bu yerdagi asosiy qoida — `react-hooks` ning tavsiya
 * etilgan to'plami, va u OGOHLANTIRISH emas, XATO darajasida.
 */

import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'public'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.es2021 },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // ⚠️ Loyihaning eng qimmat xatosi shu qoida ostida. Pasaytirilmasin.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // Fast Refresh faqat komponent eksport qilingan faylda ishlaydi.
      // Ogohlantirish darajasida: hook va komponentni bitta faylda
      // saqlash ba'zan ataylab qilingan (masalan `CallAudioPlayer`).
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // `_` bilan boshlangan argument — ataylab ishlatilmagan
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
)
