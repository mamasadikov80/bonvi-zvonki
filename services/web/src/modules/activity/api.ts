/**
 * Qo'ng'iroq faolligi — hajm va javobgarlik ko'rsatkichlari.
 *
 * Baholashdan MUSTAQIL: baholash «suhbat qanday o'tdi?» degan savolga
 * javob beradi, bu esa boshqasiga — kim kimga qancha qo'ng'iroq qildi,
 * nechtasi javobsiz qoldi, javobsizlarga qaytib chiqildimi.
 */

import { useQuery } from '@tanstack/react-query'

import { api } from '@/shared/api/client'

/** Hisobot davrlari — shef so'ragan to'rt oyna. */
export const PERIODS = [1, 7, 15, 30] as const
export type Period = (typeof PERIODS)[number]

export interface ActivityRow {
  agent_id: string
  agent_name: string
  region: string | null

  /** Xodim mijozlarga qilgan qo'ng'iroqlar */
  outbound_total: number
  outbound_answered: number
  /** Mijoz ko'tarmadi. ⚠️ Bu «propushenniy» EMAS — xodimning aybi ham
   *  emas: odam band bo'lishi yoki telefoni o'chiq bo'lishi mumkin. */
  outbound_no_answer: number

  /** Mijozlar xodimga qilgan qo'ng'iroqlar */
  inbound_total: number
  /** Javob holati BILINGAN kiruvchilar. ⚠️ Foizlar shundan hisoblanadi,
   *  `inbound_total` dan emas: o'lchandi, farq olti barobar (4.6% ↔ 29%).
   *  Noma'lum qatorlarni bo'linuvchida qoldirish foizni sun'iy
   *  pasaytiradi — ya'ni xato xushomad qiladigan tomonga qarab bo'ladi. */
  inbound_known: number
  inbound_answered: number
  /** KIRUVCHI + javobsiz = «propushenniy». Kompaniya javobgarligi. */
  missed: number

  /** Javobsiz HODISALARdan keyin aloqa bo'lganlari */
  missed_called_back: number
  /** Raqami BOR javobsiz hodisalar — `missed_open` shundan hisoblanadi.
   *  Raqamsiz javobsiz qo'ng'iroqqa qaytish imkonsiz. */
  missed_addressable: number
  /** Javobsiz qolib, keyin ham aloqa bo'lmagan hodisalar (hajm) */
  missed_open: number

  /* ── Mijoz darajasi — ASOSIY ko'rsatkich ──────────────────
     Mijoz bog'lanolmasa qayta-qayta uriniadi (o'lchandi: o'rtacha 1.8
     marta). Hodisalarni sanash bir odamning muammosini bir necha marta
     hisoblardi. Yomonroq holat: mijoz 4 marta qo'ng'iroq qilib
     4-chisida javob olgan bo'lsa, hodisa hisobi «3 javobsiz, 75%» deb
     ko'rsatadi — holbuki mijoz BOG'LANGAN. */

  /** Bog'lanolmagan MIJOZLAR soni */
  missed_clients: number
  clients_reached: number
  /** ⚠️ HISOBOTNING ASOSIY RAQAMI — yo'qolgan savdo imkoniyati */
  clients_unreached: number

  /** Kiruvchilarning qancha foizi javobsiz qolgan. `null` — kiruvchi yo'q */
  missed_rate: number | null
  /** Javobsizlarning qancha foiziga qaytilgan. `null` — javobsiz yo'q */
  callback_rate: number | null

  total: number
  talk_seconds: number
  /** `answered` noma'lum qatorlar — hisobda SANALMAYDI. Ustun paydo
   *  bo'lishidan oldingi ma'lumot; qayta sinxronizatsiya to'ldiradi. */
  unknown: number
  /** Yo'nalish bo'yicha noma'lumlar. Ular bo'lmasa chiquvchi qatori
   *  ekranda yig'ilmasdi va son o'z-o'ziga zid ko'rinardi. */
  unknown_in: number
  unknown_out: number
}

/** Bir kunlik hajm — grafik uchun.
 *
 *  Faqat hajm: mijoz darajasidagi hisob bu yerda YO'Q va ataylab — u
 *  kun chegarasida buziladi (mijoz kechqurun qo'ng'iroq qilib, ertalab
 *  javob olishi mumkin) va grafikdagi raqam kartadagi bilan mos
 *  kelmasdi. */
export interface ActivityDay {
  day: string
  inbound: number
  inbound_answered: number
  missed: number
  outbound: number
  outbound_no_answer: number
}

/** Soatlik kesim — qaysi soatda mijozlar bog'lanolmaydi.
 *
 *  ⚠️ Soat MAHALLIY vaqtda (Asia/Tashkent). Bu razrez rahbarga eng
 *  amaliy narsani ko'rsatadi: o'lchandi, tushlik payti javobsizlar
 *  35%, ertalab 07:00 da 74%. Kunlik o'rtacha 29% bu tafovutni
 *  butunlay yashirardi. */
/** ⚠️ Shakli `ActivityDay` bilan AYNAN bir xil — bitta grafik
 *  ikkalasini ham chizadi va kesim almashganda ustunlar o'zgarmasligi
 *  kerak. Aks holda foydalanuvchi kesimni almashtirganda sonlar sakrab,
 *  tizimga ishonchi qolmasdi. */
export interface ActivityHour {
  hour: number
  inbound: number
  inbound_answered: number
  missed: number
  outbound: number
  outbound_no_answer: number
  missed_rate: number | null
}

export interface ActivityReport {
  days: number
  date_from: string
  date_to: string
  /** Qaytib aloqaga chiqish shu muddat ichida hisobga olinadi */
  callback_window_hours: number
  callback_median_minutes: number | null
  days_series: ActivityDay[]
  hours_series: ActivityHour[]
  agents: ActivityRow[]
  total: ActivityRow
}

export interface ActivityQuery {
  days: number
  /** Aniq oraliq — berilsa `days` ni bekor qiladi */
  date_from?: string
  date_to?: string
  agent_ids?: string[]
  regions?: string[]
}

export const useActivity = (query: ActivityQuery, enabled = true) =>
  useQuery({
    queryKey: ['activity', query],
    queryFn: () => api.get<ActivityReport>('/analytics/activity', query as never),
    enabled,
    staleTime: 60_000,
  })

/** Bog'lanolmagan bitta mijoz — TEKSHIRISH uchun tafsilot.
 *
 *  Jadvaldagi «100%» yoki «3 mijoz bog'lanmagan» degan son ishonchsiz
 *  ko'rinishi mumkin: xodimda 15 javobsiz qo'ng'iroq bo'lib, qaytish
 *  darajasi 100% bo'lishi g'alati tuyuladi. Aslida to'g'ri — 15 hodisa
 *  9 xil mijozdan kelgan va hammasi bilan gaplashilgan. Buni isbotlab
 *  ko'rsatmasa raqamga ishonch bo'lmaydi, ayniqsa rahbar oldida. */
export interface MissedClient {
  phone: string
  client_name: string | null
  /** Necha marta javobsiz qo'ng'iroq qilgan */
  attempts: number
  first_missed_at: string
  last_missed_at: string
  /** `null` — HALI bog'lanilmagan */
  contacted_at: string | null
  /** Kim bilan aloqa bo'lgan. Boshqa xodim bo'lishi mumkin */
  contacted_by: string | null
  /** `true` — mijoz o'zi qayta urinib javob olgan; `false` — xodim qaytardi */
  contact_inbound: boolean | null
  minutes_to_contact: number | null
}

export interface MissedClientsReport {
  agent_id: string
  agent_name: string
  date_from: string
  date_to: string
  callback_window_hours: number
  clients: MissedClient[]
  unreached: number
}

export const useMissedClients = (agentId: string | null, query: ActivityQuery) =>
  useQuery({
    queryKey: ['activity', 'missed-clients', agentId, query],
    queryFn: () =>
      api.get<MissedClientsReport>('/analytics/activity/missed-clients', {
        agent_id: agentId,
        days: query.days,
        date_from: query.date_from,
        date_to: query.date_to,
      } as never),
    enabled: Boolean(agentId),
  })
