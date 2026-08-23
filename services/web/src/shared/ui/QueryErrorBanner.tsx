/**
 * Ma'lumot yuklanmaganini KO'RSATADIGAN chiziq.
 *
 * NEGA KERAK. TanStack Query xato bo'lganda `data` ni `undefined`
 * qoldiradi. Sahifalar esa `data ?? []` yozadi — natijada server
 * yiqilgani «bo'sh ro'yxat» bo'lib ko'rinadi. Foydalanuvchi uchun bu
 * ikki butunlay boshqa narsa: «bu davrda qo'ng'iroq bo'lmagan» va
 * «ma'lumotni olib bo'lmadi». Farqni ko'rsatmaslik eng yomon xato turi
 * — chunki hech kim shikoyat qilmaydi, shunchaki noto'g'ri xulosa
 * chiqaradi.
 *
 * NEGA HAR SAHIFAGA ALOHIDA EMAS. Har bir sahifada `isError` ni qo'lda
 * tekshirish 9 joyda takrorlanardi va yangi sahifada UNUTILARDI —
 * unutilganini esa hech narsa ko'rsatmasdi. Bu chiziq navbatni
 * BUTUNLIGICHA kuzatadi: qaysi so'rov yiqilsa ham ko'rinadi.
 *
 * Kirish sahifasi bundan mustasno emas, lekin unga kerak ham emas: u
 * xatoni o'zi ko'rsatadi (`auth.invalidCredentials`).
 */

import { onlineManager, useQueryClient } from '@tanstack/react-query'
import { CloudOff, RefreshCw, WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/shared/api/client'
import { cn } from '@/shared/lib/utils'

/**
 * KUTILGAN javoblar — nosozlik EMAS.
 *
 * `404` — «bunday mijoz yo'q». Bu server yiqilgani emas, savolga
 * berilgan to'g'ri javob; sahifaning o'zi uni tushunarli matn bilan
 * ko'rsatadi (`clients.notFound`). Chiziq esa yuqorida «ma'lumotni
 * olib bo'lmadi» deb yozib, foydalanuvchini dasturiy xatolik bor deb
 * o'ylashga majbur qilardi.
 *
 * `403` — «bu bo'lim senga ochiq emas» (masalan savdo xodimi mijoz
 * kartochkasidagi savdo nazoratini so'rasa). Ruxsat chegarasi ham
 * loyihalangan xatti-harakat.
 *
 * `422` — so'rov shakli noto'g'ri (`/clients/undefined` kabi). Bu
 * KODDAGI xato va uni tuzatish kerak, lekin foydalanuvchiga «tarmoq
 * yiqildi» deb ko'rsatish uni chalg'itadi.
 *
 * ⚠️ Ro'yxat ATAYLAB qisqa. `5xx` va tarmoq uzilishi baribir
 * ko'rinadi — chiziqning butun ma'nosi «bo'sh ro'yxat» bilan «server
 * yiqildi» ni ajratish. `401` bu yerga umuman yetib kelmaydi:
 * `api/client.ts` uni loginga otib yuboradi.
 */
const EXPECTED = new Set([403, 404, 422])

/** Chiziq shu so'rovni sanashi kerakmi. */
const isFailure = (error: unknown): boolean =>
  !(error instanceof ApiError) || !EXPECTED.has(error.status)

export function QueryErrorBanner() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [failed, setFailed] = useState(0)
  const [offline, setOffline] = useState(() => !onlineManager.isOnline())
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    const cache = client.getQueryCache()
    const sanash = () => {
      /* FAQAT kuzatilayotgan so'rovlar. Keshdagi eski, hech kim
         ko'rmayotgan xato chiziqni bejiz yoqib turardi — masalan
         foydalanuvchi allaqachon boshqa bo'limga o'tib ketgan. */
      setFailed(
        cache
          .getAll()
          .filter(
            (q) =>
              q.state.status === 'error' &&
              q.getObserversCount() > 0 &&
              isFailure(q.state.error),
          ).length,
      )
    }
    sanash()
    const unsubscribe = cache.subscribe(sanash)
    return unsubscribe
  }, [client])

  useEffect(() => onlineManager.subscribe((online) => setOffline(!online)), [])

  if (!offline && failed === 0) return null

  const retry = async () => {
    setRetrying(true)
    try {
      // Faqat xato holatidagilar — muvaffaqiyatli so'rovlar bejiz
      // qayta yuborilmaydi.
      //
      // ⚠️ `stale` filtri QO'YILMAYDI. `stale: false` yozilsa «eskirmagan»
      // so'rovlar tanlanardi, xato holatidagi so'rov esa odatda eskirgan
      // hisoblanadi — natijada tugma bosilardi va hech narsa qilmasdi.
      await client.refetchQueries({
        type: 'active',
        // Kutilgan xatolar (404/403/422) chiziqni yoqmaydi, demak
        // ularni qayta so'rashning ham ma'nosi yo'q: javob o'zgarmaydi.
        predicate: (q) => q.state.status === 'error' && isFailure(q.state.error),
      })
    } finally {
      setRetrying(false)
    }
  }

  const Icon = offline ? WifiOff : CloudOff

  return (
    <div
      role="status"
      className={cn(
        'flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl px-3.5 py-2.5',
        'bg-bad/10 text-xs',
      )}
    >
      <Icon className="size-4 shrink-0 text-bad" />
      <span className="min-w-0 flex-1 leading-relaxed">
        {offline ? t('errors.offline') : t('errors.loadFailed', { count: failed })}
      </span>
      {!offline && (
        <button
          onClick={retry}
          disabled={retrying}
          className={cn(
            'inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg bg-surface px-2.5 font-medium',
            'transition-all duration-250 ease-ios active:scale-[0.97]',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          <RefreshCw className={cn('size-3', retrying && 'animate-spin')} />
          {t('errors.retry')}
        </button>
      )}
    </div>
  )
}
