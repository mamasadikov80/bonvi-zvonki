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

import { cn } from '@/shared/lib/utils'

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
          .filter((q) => q.state.status === 'error' && q.getObserversCount() > 0).length,
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
        predicate: (q) => q.state.status === 'error',
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
