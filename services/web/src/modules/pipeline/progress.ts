/**
 * Ommaviy baholash jarayonining holati.
 *
 * NEGA ALOHIDA STORE. Baholash ORQA FONDA ketadi: endpoint «navbatga
 * qo'ydim» deb darhol javob qaytaradi, ish esa Celery workerlarida
 * daqiqalar davomida bajariladi. Ilgari jarayonni faqat modal oyna
 * ichida ko'rish mumkin edi — oyna yopilishi bilan admin qancha
 * qolganini bilmay qolardi.
 *
 * Endi holat oynadan tashqarida yashaydi va qo'ng'iroqlar sahifasining
 * tepasida BITTA umumiy chiziq bo'lib ko'rinadi: 50 ta qo'ng'iroq
 * yuborilsa ham, chiziq o'shaning hammasini 0% dan 100% gacha
 * ko'rsatadi.
 *
 * ⚠️ PROGRESS «QOLGAN» DAN EMAS, «BAJARILGAN» DAN HISOBLANADI.
 * Bu tajribadan chiqqan qaror. `/pipeline/status` dagi bosqich
 * sanoqlari (`queued`, `transcribing`, `scoring`) faqat WORKER ISHNI
 * BOSHLAGANDAN keyin paydo bo'ladi — Redis navbatida kutayotgan
 * vazifalar u yerda umuman ko'rinmaydi. Haqiqiy sinovda 3 ta
 * qo'ng'iroq yuborilganda «qolgan» boshidan oxirigacha 0 bo'lib
 * turdi, holbuki `completed` 39 dan 48 ga chiqdi. Ya'ni «qolgan» ga
 * qarab chizilgan chiziq darhol 100% ko'rsatib, yolg'on gapirardi.
 *
 * Shuning uchun boshlanishida TUGAGAN ishlar soni eslab qolinadi va
 * progress o'shandan beri qancha ish tugaganidan hisoblanadi.
 *
 * `sessionStorage` — sahifa yangilansa yoki boshqa bo'limga o'tib
 * qaytilsa jarayon yo'qolmasin. Navbat baribir serverda ketyapti.
 */

import { create } from 'zustand'

const STORAGE_KEY = 'zvonki.scoring-batch'

/** Qotib qolgan yozuv abadiy osilib turmasin */
const MAX_AGE_MS = 60 * 60 * 1000

/** Navbat bo'sh bo'lsa ham shuncha vaqt kutamiz: worker vazifani
 *  Redis'dan olguncha bir necha soniya o'tadi va o'sha oynada
 *  «hammasi bo'sh» ko'rinadi — chiziq bejiz tugab qolmasin */
const IDLE_GRACE_MS = 45_000

export interface ScoringBatch {
  /** Navbatga qo'yilgan qo'ng'iroqlar soni — chiziqning 100% i */
  total: number
  startedAt: number

  /** Boshlanish paytidagi TUGAGAN ishlar soni.
   *
   *  `null` — hali birinchi holat javobi kelmagan. Progress shu
   *  qiymatdan boshlab hisoblanadi, ya'ni oldingi ishlar aralashmaydi. */
  baseline: number | null

  /** Shu paytgacha ko'rilgan eng katta bajarilgan son.
   *
   *  ⚠️ Chiziq ORQAGA QAYTMASLIGI uchun. Sanoq global: yonma-yon
   *  boshqa ish ketsa raqamlar sakrashi mumkin, lekin ekranda
   *  progress orqaga sirg'alsa «nimadir buzildi» degan taassurot
   *  qoladi. */
  done: number
}

/** `/pipeline/status` dan olinadigan, progress uchun kerak bo'lgan qism */
export interface QueueSnapshot {
  /** Terminal holatga yetgan ishlar: tugagan + yiqilgan + o'tkazilgan */
  finishedTotal: number
  /** Hozir harakatda: Redis navbati + workerdagi vazifalar + bosqichlar */
  inFlight: number
}

interface State {
  batch: ScoringBatch | null
  start: (total: number) => void
  observe: (snapshot: QueueSnapshot) => void
  stop: () => void
}

function load(): ScoringBatch | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as ScoringBatch
    if (!parsed?.total || Date.now() - parsed.startedAt > MAX_AGE_MS) {
      sessionStorage.removeItem(STORAGE_KEY)
      return null
    }
    return parsed
  } catch {
    return null
  }
}

function save(batch: ScoringBatch | null) {
  try {
    if (batch) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(batch))
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* Maxfiy rejimda `sessionStorage` yo'q — jarayon baribir ishlaydi */
  }
}

export const useScoringBatch = create<State>((set, get) => ({
  batch: load(),

  start: (total) => {
    if (total <= 0) return
    const batch: ScoringBatch = {
      total,
      startedAt: Date.now(),
      baseline: null,
      done: 0,
    }
    save(batch)
    set({ batch })
  },

  observe: ({ finishedTotal }) => {
    const batch = get().batch
    if (!batch) return

    // Birinchi javob — sanoqning boshlanish nuqtasi
    if (batch.baseline === null) {
      const next = { ...batch, baseline: finishedTotal }
      save(next)
      set({ batch: next })
      return
    }

    const done = Math.max(
      batch.done,
      Math.min(batch.total, finishedTotal - batch.baseline),
    )
    if (done === batch.done) return

    const next = { ...batch, done }
    save(next)
    set({ batch: next })
  },

  stop: () => {
    save(null)
    set({ batch: null })
  },
}))

/** 0..100 — chiziq shuncha to'ladi */
export function batchPercent(batch: ScoringBatch | null): number {
  if (!batch || batch.total <= 0) return 0
  return Math.round((batch.done / batch.total) * 100)
}

/**
 * Jarayon tugadimi.
 *
 * Ikki yo'l bilan tugaydi:
 *   1. hamma ish bajarildi (`done >= total`) — odatiy holat;
 *   2. navbat bo'sh va uzoq vaqt hech narsa o'zgarmadi — masalan
 *      vazifaning bir qismi yo'qolgan bo'lsa. Chiziq abadiy osilib
 *      turmasligi kerak.
 */
export function batchFinished(
  batch: ScoringBatch | null,
  snapshot: QueueSnapshot | null,
): boolean {
  if (!batch || batch.baseline === null) return false
  if (batch.done >= batch.total) return true

  if (!snapshot || snapshot.inFlight > 0) return false
  return Date.now() - batch.startedAt > IDLE_GRACE_MS
}
