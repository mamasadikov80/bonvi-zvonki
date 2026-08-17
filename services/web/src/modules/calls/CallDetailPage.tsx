import {
  AlertTriangle,
  Lightbulb,
  Package,
  ShieldQuestion,
  Sparkles,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import type { TFunction } from 'i18next'

import { useAuth } from '@/modules/auth/store'
import { useCall, type RedFlag } from '@/modules/calls/api'
import { useRetryCall } from '@/modules/pipeline/api'
import {
  CallAudioPlayer,
  useCallAudio,
  type AudioMark,
} from '@/modules/calls/CallAudioPlayer'
import { CallTypeBadge } from '@/modules/calls/CallTypeBadge'
import { Page, PageHeader } from '@/shared/layout/Page'
import { useDateFormat } from '@/shared/lib/date'
import { cn, formatDuration, scoreTone, TONE_CLASS } from '@/shared/lib/utils'
import { Avatar, MiniBar, ScoreRing } from '@/shared/ui/dataviz'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Skeleton,
} from '@/shared/ui/primitives'

const BLOCK_LABEL: Record<string, string> = {
  script: 'Skript va struktura',
  communication: 'Muloqot madaniyati',
  resolution: 'Muammoni hal qilish',
  sales_skill: 'Savdo qobiliyati',
}

const BLOCK_MAX: Record<string, number> = {
  script: 25,
  communication: 25,
  resolution: 25,
  sales_skill: 25,
}

/* ── Transkriptni o'qish ───────────────────────────────────────

   ⚠️ FORMAT HAR PROVAYDERDA BOSHQACHA. Ilgari bu yerda BITTA qat'iy
   shablon bor edi — «[MM:SS] Kim: matn» — va unga tushmagan qator
   JIMGINA tashlab yuborilardi. Gemini esa vaqtsiz «SPEAKER_0: matn»
   qaytaradi, Whisper umuman yorliqsiz tekis matn beradi. Natijada
   bazada 6000 belgilik to'liq transkript tursa ham, sahifada
   «Ma'lumot yo'q» ko'rinardi va baho qayerdan chiqqani tushunarsiz
   bo'lardi.

   Endi hamma shakl o'qiladi:
     [12:34] Xodim: matn     → vaqt + gapiruvchi
     SPEAKER_0: 12:34 matn   → gapiruvchi, keyin qavssiz vaqt
     SPEAKER_0: matn         → gapiruvchi, vaqtsiz
     shunchaki matn          → yorliqsiz xatboshi

   ⚠️ Vaqt gapiruvchining IKKALA tomonida ham qidiriladi. Promptda
   «[MM:SS] SPEAKER_0: matn» so'ralsa ham, Gemini amalda uni
   «SPEAKER_0: 00:00 matn» qilib qaytaradi — bir joyda qidirilganda
   vaqt matn ichida qolib ketardi va sakrash ishlamasdi.

   Vaqt bo'lmasa qator bosilmaydigan bo'ladi (sakrash mumkin emas),
   lekin MATN har doim ko'rinadi. */

type SpeakerRole = 'agent' | 'client' | 'unknown'

interface Segment {
  /** `null` — provayder vaqt bermagan, sakrash mumkin emas */
  time: string | null
  seconds: number | null
  /** Xom yorliq (`SPEAKER_0`, `Xodim`…). `null` — yorliqsiz matn */
  speaker: string | null
  /** Paydo bo'lish tartibidagi ovoz raqami — chap/o'ng taqsimlash uchun */
  voice: number | null
  role: SpeakerRole
  text: string
}

//: `[12:34]`, `(1:02:03)` — qavs aniq belgi, shubha yo'q
/** Qoidabuzarlik yorlig'i — uch bosqichli zaxira.
 *
 *  1. `label` (backend rubrikadan qo'shgan) — admin yaratgan qoidalar
 *     uchun YAGONA manba, tarjima fayli ularni bilmaydi;
 *  2. tarjima — standart qoidalar uchun (tilga moslashadi);
 *  3. kalitning o'zi — qoida rubrikadan o'chirilgan bo'lsa ham
 *     menejer nima bo'lganini ko'rishi kerak. Bo'sh joy qoldirish
 *     eng yomon variant: bayroq bor, nomi yo'q. */
function flagLabel(t: TFunction, flag: RedFlag): string {
  if (flag.label) return flag.label
  return t(`calls.redFlagTypes.${flag.type}`, { defaultValue: flag.type })
}

const BRACKETED_TIME = /^[[(](\d{1,2}):([0-5]\d)(?::([0-5]\d))?[\])]\s*[-–—]?\s*(.*)$/
//: `12:34 matn` — qavssiz. Ortidan probel SHART, aks holda oddiy
//: sondan farqi qolmaydi
const BARE_TIME = /^(\d{1,2}):([0-5]\d)(?::([0-5]\d))?\s+(.*)$/
//: Yorliq: harf/raqam/`_`/probel, ko'pi bilan uch so'z va 32 belgi
const LABELLED = /^([\p{L}\p{N}_][\p{L}\p{N}_ .'-]{0,31}):\s*(.*)$/u

interface TimeCut {
  time: string
  seconds: number
  rest: string
}

/** Matn boshidagi vaqt belgisini ajratib oladi. Bo'lmasa — `null`.
 *
 *  `limit` — qo'ng'iroq davomiyligi. QAVSSIZ vaqt uchun u majburiy
 *  chegara: «15:30 da kelaman» degan jumla 5 daqiqalik qo'ng'iroqda
 *  vaqt belgisi bo'lolmaydi, demak u matnning bir qismi. Qavsli
 *  shaklga bu tekshiruv qo'llanmaydi — qavsning o'zi niyatni aytadi. */
function takeTime(text: string, limit: number): TimeCut | null {
  for (const [pattern, bounded] of [
    [BRACKETED_TIME, false],
    [BARE_TIME, true],
  ] as const) {
    const match = text.match(pattern)
    if (!match) continue

    const [, a, b, c, rest] = match
    // Uch guruh bo'lsa `H:MM:SS`, aks holda `MM:SS`
    const seconds = c
      ? Number(a) * 3600 + Number(b) * 60 + Number(c)
      : Number(a) * 60 + Number(b)

    // Yozuv metama'lumotdan bir necha soniyaga uzun bo'lishi mumkin
    if (bounded && limit > 0 && seconds > limit + 5) continue

    const label = c
      ? `${a}:${b.padStart(2, '0')}:${c}`
      : `${a.padStart(2, '0')}:${b}`
    return { time: label, seconds, rest: rest.trim() }
  }
  return null
}

const AGENT_WORDS = /xodim|operator|menejer|agent|sotuvchi|менеджер|оператор/i
const CLIENT_WORDS = /mijoz|mijozi|client|xaridor|клиент|покупатель/i

function labelLike(value: string): boolean {
  return value.trim().split(/\s+/).length <= 3
}

function parseTranscript(raw: string | null, durationSec = 0): Segment[] {
  if (!raw) return []

  const lines = raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  if (!lines.length) return []

  /* ── Yorliqli rejimmi? ──────────────────────────────────────

     Qaror QATOR ULUSHIGA qarab qilinmaydi. Ilgari «qatorlarning 60% i
     yorliqli bo'lsin» degan shart bor edi va u amalda teskari ish
     qildi: Gemini transkriptning boshida `SPEAKER_0:` yozib, keyin
     uni tashlab yuboradi — 151 qatordan 9 tasida yorliq bo'ldi, shart
     bajarilmadi va BOR yorliqlar ham bekor qilindi. Ya'ni model biroz
     dangasalik qilgani uchun butun suhbat bir tomonga yig'ilib qoldi.

     To'g'ri belgi — TAKRORLANISH. Haqiqiy suhbatda bir nechta yorliq
     ko'p marta qaytariladi (SPEAKER_0, SPEAKER_1). Oddiy matndagi
     tasodifiy ikki nuqta («Narxi: 320», «Rahmat: kelishdik») esa har
     safar boshqa «yorliq» beradi va hech biri takrorlanmaydi. */
  const counts = new Map<string, number>()
  for (const line of lines) {
    const body = takeTime(line, durationSec)?.rest ?? line
    const match = body.match(LABELLED)
    if (match && labelLike(match[1])) {
      const key = match[1].trim().toLowerCase()
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
  }
  const labelled = [...counts.values()].reduce((sum, n) => sum + n, 0)
  const speakerMode =
    counts.size > 0 &&
    // Suhbatda gapiruvchilar soni cheklangan — o'nlab «yorliq»
    // bo'lsa, bu suhbat emas, oddiy matn
    counts.size <= 8 &&
    // Yo bittasi qaytarilgan, yo hamma qator yorliqli
    ([...counts.values()].some((n) => n >= 2) || labelled === lines.length)

  const voices = new Map<string, number>()

  return lines.map((line) => {
    let rest = line
    let time: string | null = null
    let seconds: number | null = null

    // 1) Vaqt gapiruvchidan OLDIN: «[12:34] SPEAKER_0: matn»
    const before = takeTime(rest, durationSec)
    if (before) {
      time = before.time
      seconds = before.seconds
      rest = before.rest
    }

    let speaker: string | null = null
    let voice: number | null = null
    if (speakerMode) {
      const match = rest.match(LABELLED)
      if (match && labelLike(match[1])) {
        speaker = match[1].trim()
        rest = match[2].trim()
        const key = speaker.toLowerCase()
        if (!voices.has(key)) voices.set(key, voices.size)
        voice = voices.get(key) ?? null
      }
    }

    // 2) Vaqt gapiruvchidan KEYIN: «SPEAKER_0: 12:34 matn».
    //    Gemini amalda aynan shunday qaytaradi.
    if (seconds === null) {
      const after = takeTime(rest, durationSec)
      if (after) {
        time = after.time
        seconds = after.seconds
        rest = after.rest
      }
    }

    const role: SpeakerRole = !speaker
      ? 'unknown'
      : AGENT_WORDS.test(speaker)
        ? 'agent'
        : CLIENT_WORDS.test(speaker)
          ? 'client'
          : 'unknown'

    return { time, seconds, speaker, voice, role, text: rest }
  })
}

export function CallDetailPage() {
  const { t } = useTranslation()
  const { callId } = useParams<{ callId: string }>()
  const fmt = useDateFormat()
  const call = useCall(callId)

  // Qayta baholash — `agents:sync` ruxsati borlarda. Savdo xodimi va
  // kuzatuvchida bu ruxsat yo'q, ya'ni tugma umuman chizilmaydi.
  const { can } = useAuth()
  const canRescore = can('agents:sync')
  const retry = useRetryCall()
  // Navbatga qo'yilgach tugma qaytadan bosilmasin: natija bir necha
  // daqiqadan keyin keladi va takroriy bosish ortiqcha xarajat bo'lardi
  const [queued, setQueued] = useState(false)

  // Transkript qutisi va undagi joriy qator — avtomatik ergashish uchun.
  // Qator vaqti borligiga qarab `<button>` yoki `<div>` bo'ladi, shuning
  // uchun umumiy `HTMLElement`.
  const bodyRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLElement | null>(null)

  // Yozuv holati sahifa ochilishi bilan tekshiriladi: `<audio>` elementi
  // xato SABABINI aytmaydi, backend esa aytadi (yozuv yo'q / sozlanmagan)
  const audio = useCallAudio(callId, call.data?.duration_sec ?? 0)

  /* ⚠️ HOOKLAR SHU YERDA TUGAYDI — pastda `return` lar boshlanadi.
     Hook shartli chaqirilsa (yoki `return` dan keyin qolsa) React
     «Rendered more hooks than during the previous render» bilan butun
     sahifani yiqitadi: birinchi renderda ma'lumot hali yo'q, ikkinchisida
     bor — hooklar soni farq qiladi. Shuning uchun transkriptga bog'liq
     hisob-kitob ham `call.data` bormi-yo'qmi, HAR DOIM bajariladi. */

  const data = call.data

  /* Vaqt belgisining yuqori chegarasi.
     ⚠️ `duration_sec` YETMAYDI. MoyZvonki bu maydonda faqat SUHBAT
     vaqtini beradi, audio yozuv esa jiringlash/kutishni ham o'z ichiga
     oladi — haqiqiy ma'lumotda farq 7 barobargacha chiqdi (33 soniyalik
     qo'ng'iroqda transkript 238-soniyagacha ketgan). Faqat `duration_sec`
     ga qarasak, qavssiz vaqt belgilari «bu davomiylikdan uzun, demak
     vaqt emas» deb rad etilardi va o'sha qatorlar sakrash imkonini
     yo'qotardi — natijada avtomatik ergashish ba'zi qo'ng'iroqlarda
     ishlamasdi. Pleer metama'lumotni o'qigach haqiqiy uzunlikni biladi,
     shuning uchun ikkovining kattasi olinadi. */
  const timeLimit = Math.max(data?.duration_sec ?? 0, audio.duration || 0)

  // Ijro paytida sahifa sekundiga bir necha marta qayta chiziladi —
  // transkriptni har safar qaytadan ajratmaymiz
  const segments = useMemo(
    () => parseTranscript(data?.transcript ?? null, timeLimit),
    [data?.transcript, timeLimit],
  )

  /* Transkriptda qaysi qator hozir o'qilyapti.
     Segmentlar vaqt bo'yicha tartiblangan, shuning uchun joriy vaqtdan
     oldingi OXIRGI segment — aynan shu payt aytilayotgani. */
  const activeIndex = segments.reduce(
    (found, segment, index) =>
      segment.seconds !== null && audio.currentTime + 0.25 >= segment.seconds
        ? index
        : found,
    -1,
  )
  const followAudio = audio.playing || audio.currentTime > 0

  /* Ijro davomida joriy qator KO'RINIB tursin.
     Faqat transkript qutisining `scrollTop` i o'zgaradi — sahifa
     qimirlamaydi, ya'ni foydalanuvchi boshqa joyni o'qiyotgan bo'lsa
     ekran uning tagidan sirg'alib ketmaydi. */
  useEffect(() => {
    if (!followAudio || activeIndex < 0) return
    const box = bodyRef.current
    const row = activeRef.current
    if (!box || !row) return

    /* ⚠️ O'LCHOV `getBoundingClientRect` BILAN, `offsetTop` bilan EMAS.
       `offsetTop` eng yaqin POZITSIYALANGAN ajdodga nisbatan o'lchanadi
       va shu sababli xatoga juda moyil: ilgari bu yerda
       `row.offsetTop − box.offsetTop` turardi. Konteynerga `relative`
       qo'shilgach `row.offsetTop` allaqachon konteynerga nisbatan
       bo'lib qoldi va ayirish IKKI MARTA bajarilib, sakrash
       `box.offsetTop` qadar xato joyga tushardi. Xato sahifa
       tuzilishiga bog'liq — shuning uchun ba'zi qo'ng'iroqlarda
       to'g'ri, ba'zilarida noto'g'ri ishlardi.

       Rect ayirmasi esa hech qanday `offsetParent` ga bog'liq emas. */
    const top =
      row.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop
    const bottom = top + row.offsetHeight

    // Chetiga tegib turgan qator ham «ko'rinmagan» hisoblanadi:
    // yarim ko'rinib turgan gapni o'qib bo'lmaydi
    const pad = 12
    const seen =
      top >= box.scrollTop + pad &&
      bottom <= box.scrollTop + box.clientHeight - pad
    if (seen) return

    box.scrollTo({
      // Uchdan bir baland: keyingi qatorlar ham oldindan ko'rinadi
      top: Math.max(0, top - box.clientHeight / 3),
      behavior: 'smooth',
    })
  }, [activeIndex, followAudio])

  if (call.isLoading) {
    return (
      <Page>
        <Skeleton className="h-9 w-72" />
        <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
          <Skeleton className="h-[560px] w-full" />
          <Skeleton className="h-[560px] w-full" />
        </div>
      </Page>
    )
  }

  if (!data) {
    return (
      <Page>
        <EmptyState message={t('table.empty')} />
      </Page>
    )
  }

  const score = data.score
  const tone = scoreTone(score?.overall_score) as 'accent' | 'good' | 'warn' | 'bad'
  const started = new Date(data.started_at)

  // Red flag'larni soniyaga aylantirib timeline'da belgilaymiz
  const flagMarks: AudioMark[] = (score?.red_flags ?? [])
    .map((flag) => {
      const [mm, ss] = (flag.timestamp ?? '').split(':').map(Number)
      if (Number.isNaN(mm) || Number.isNaN(ss)) return null
      return {
        seconds: mm * 60 + ss,
        label: `${flag.timestamp} · ${
          flag.quote ??
          flagLabel(t, flag)
        }`,
      }
    })
    .filter((mark): mark is AudioMark => mark !== null)

  /* Vaqt belgilari bormi — «bosib o'tish» maslahati faqat shunda ma'noli */
  const seekable = segments.some((segment) => segment.seconds !== null)

  return (
    <Page>
      {/* Sarlavhadagi mijoz: katalogdagi nom → MoyZvonki bergan nom → raqam */}
      <PageHeader
        title={`${data.agent.full_name} ↔ ${
          data.client?.name ?? data.client_name ?? data.client_phone ?? '—'
        }`}
        subtitle={`${fmt.dateTime(started)} · ${formatDuration(data.duration_sec)}`}
        actions={
          <>
            <CallTypeBadge type={data.call_type} />
            {score?.needs_review && <Badge tone="warn">{t('calls.needsReview')}</Badge>}
            <Badge tone={tone === 'bad' ? 'bad' : 'accent'}>
              <span className="tnum font-semibold">{score?.overall_score ?? '—'}</span>
              /100
            </Badge>
            {/* Qayta baholash — pul sarflaydigan amal, shuning uchun
                `agents:sync` ruxsatiga bog'langan (sinxronizatsiya bilan
                bir xil kalit). Natija darhol kelmaydi: navbatga
                qo'yiladi, shuning uchun tugma «yuborildi» deb yozadi. */}
            {canRescore && (
              <Button
                variant="secondary"
                size="sm"
                disabled={retry.isPending || queued}
                onClick={() =>
                  retry.mutate(
                    { callId: callId as string },
                    { onSuccess: () => setQueued(true) },
                  )
                }
              >
                <Sparkles className="size-3.5" />
                {queued
                  ? t('pipeline.queuedShort')
                  : retry.isPending
                    ? t('pipeline.starting')
                    : t('pipeline.rescore')}
              </Button>
            )}
          </>
        }
      />

      {/* ── Yozuv: MoyZvonki'dan oqim bilan ─────────────────── */}
      <CallAudioPlayer controller={audio} marks={flagMarks} />

      {/* ── Transkript + baholash ─────────────────────────── */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px] 3xl:grid-cols-[minmax(0,1fr)_460px]">
        {/* Transkript */}
        <Card>
          <CardHeader
            title={t('calls.transcript')}
            hint={seekable ? t('calls.audio.jumpHint') : undefined}
          />
          {/* Uzun suhbat FAQAT shu panel ichida suriladi.
              Ilgari transkript qancha bo'lsa karta shuncha cho'zilardi
              va butun sahifa surilardi — o'nlab qatorni o'qish uchun
              pastga tushilsa, yonidagi baholash paneli va pleer ekrandan
              chiqib ketardi. Endi ular joyida qoladi. */}
          {/* `relative` — bezak emas, O'LCHOV uchun. Ergashish kodi
              qatorning konteyner ichidagi o'rnini `offsetTop` bilan
              hisoblaydi, u esa eng yaqin POZITSIYALANGAN ajdodga
              nisbatan o'lchanadi. Konteyner pozitsiyalanmasa, hisob
              boshqa elementdan ketadi va sakrash noto'g'ri joyga
              tushadi. */}
          <CardBody
            ref={bodyRef}
            className="relative max-h-[calc(100vh-22rem)] min-h-[18rem] space-y-3 overflow-y-auto overscroll-contain pt-3"
          >
            {!segments.length ? (
              <EmptyState message={t('common.noData')} />
            ) : (
              segments.map((segment, i) => {
                const active = followAudio && i === activeIndex
                // Chap tomon: xodim yoki birinchi ovoz. Kimligi noma'lum
                // bo'lsa ham dialog ikki tomonga bo'linadi — o'qish shu
                // bilan osonlashadi, lekin «bu xodim» deyilmaydi.
                //
                // Yorliqsiz qator (model uni tashlab ketgan) — chapda va
                // to'liq kenglikda: uni ikki tomondan biriga qo'yish
                // «bu o'sha odam gapirdi» degan yolg'on da'vo bo'lardi.
                const left =
                  segment.role === 'agent' ||
                  segment.voice === 0 ||
                  segment.voice === null
                const known = segment.role !== 'unknown'
                const label =
                  segment.speaker === null
                    ? null
                    : /^speaker[_ ]?\d+$/i.test(segment.speaker)
                      ? t('calls.voice', {
                          n: (segment.voice ?? 0) + 1,
                          defaultValue: segment.speaker,
                        })
                      : segment.speaker

                /* Vaqt bo'lsa — qatorga bosilsa audio o'sha soniyadan
                   davom etadi. Vaqtsiz transkriptda (Gemini) sakrash
                   mumkin emas, shuning uchun tugma ham emas. */
                const Row = segment.seconds !== null ? 'button' : 'div'

                return (
                  <Row
                    key={i}
                    ref={
                      active
                        ? (el: HTMLElement | null) => {
                            activeRef.current = el
                          }
                        : undefined
                    }
                    {...(segment.seconds !== null
                      ? {
                          type: 'button' as const,
                          onClick: () =>
                            audio.seek(segment.seconds as number, { play: true }),
                          title: t('calls.audio.jumpTo', { time: segment.time }),
                        }
                      : {})}
                    className={cn(
                      'flex w-full gap-3 rounded-2xl text-left',
                      'transition-all duration-250 ease-ios',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
                      left ? 'flex-row' : 'flex-row-reverse',
                    )}
                  >
                    {label !== null && (
                      <Avatar
                        name={label}
                        color={
                          segment.role === 'agent'
                            ? data.agent.color
                            : 'hsl(var(--muted))'
                        }
                        size="sm"
                      />
                    )}
                    <div
                      className={cn(
                        'max-w-[80%] rounded-2xl px-4 py-2.5',
                        'transition-all duration-250 ease-ios',
                        // Urg'u rangi FAQAT aniq tanilgan xodimda —
                        // «SPEAKER_0» kim ekani noma'lum, uni xodim
                        // deb bo'yash yolg'on bo'lardi
                        segment.role === 'agent'
                          ? 'rounded-tl-md bg-accent-soft'
                          : left
                            ? 'rounded-tl-md bg-surface-2'
                            : 'rounded-tr-md bg-surface-2',
                        !label && 'max-w-full',
                        active && 'shadow-soft ring-2 ring-accent/40',
                      )}
                    >
                      {(label !== null || segment.time) && (
                        <div className="mb-0.5 flex items-center gap-2">
                          {label !== null && (
                            <span
                              className={cn(
                                'text-2xs font-medium',
                                !known && 'text-muted',
                              )}
                            >
                              {label}
                            </span>
                          )}
                          {segment.time && (
                            <span
                              className={cn(
                                'tnum text-2xs',
                                active ? 'font-medium text-accent' : 'text-muted',
                              )}
                            >
                              {segment.time}
                            </span>
                          )}
                        </div>
                      )}
                      <p className="text-sm leading-relaxed">{segment.text}</p>
                    </div>
                  </Row>
                )
              })
            )}
          </CardBody>
        </Card>

        {/* Baholash paneli */}
        <div className="space-y-4">
          {score ? (
            <>
              <Card>
                <CardHeader title={t('calls.scoring')} />
                <CardBody className="pt-3">
                  <div className="mb-5 flex items-center gap-4">
                    <ScoreRing value={score.overall_score} tone={tone} size={64} />
                    <div>
                      <div className={cn('text-2xl font-semibold tnum', TONE_CLASS[tone])}>
                        {score.overall_score}
                        <span className="text-sm font-normal text-muted"> / 100</span>
                      </div>
                      <div className="mt-0.5 text-2xs text-muted">
                        {t('calls.confidence')}:{' '}
                        <span className="tnum">
                          {Math.round(score.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {Object.entries(score.blocks).map(([key, value]) => {
                      const max = BLOCK_MAX[key] ?? 25
                      const blockTone = scoreTone((value / max) * 100) as
                        | 'accent'
                        | 'good'
                        | 'warn'
                        | 'bad'
                      return (
                        <div key={key}>
                          <div className="mb-1 flex items-baseline justify-between gap-2">
                            <span className="text-xs">{BLOCK_LABEL[key] ?? key}</span>
                            <span className="tnum text-xs font-medium">
                              {value}
                              <span className="text-muted">/{max}</span>
                            </span>
                          </div>
                          <MiniBar value={value} max={max} tone={blockTone} width={0} />
                        </div>
                      )
                    })}
                  </div>
                </CardBody>
              </Card>

              {/* Qoidabuzarliklar */}
              {score.red_flags.length > 0 && (
                <Card>
                  <CardHeader title={t('kpi.redFlags')} />
                  <CardBody className="space-y-2 pt-3">
                    {score.red_flags.map((flag, i) => {
                      const [mm, ss] = (flag.timestamp ?? '').split(':').map(Number)
                      const seconds =
                        Number.isNaN(mm) || Number.isNaN(ss) ? null : mm * 60 + ss

                      return (
                        <button
                          key={i}
                          type="button"
                          disabled={seconds === null}
                          onClick={() =>
                            seconds !== null && audio.seek(seconds, { play: true })
                          }
                          className={cn(
                            'flex w-full items-start gap-2.5 rounded-xl bg-bad/5 p-3 text-left ring-1 ring-bad/20',
                            'transition-all duration-250 ease-ios',
                            seconds !== null && 'hover:bg-bad/[0.09] active:scale-[0.99]',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bad/40',
                          )}
                        >
                          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium">
                                {flagLabel(t, flag)}
                              </span>
                              {flag.timestamp && (
                                <span className="tnum text-2xs text-muted">
                                  {flag.timestamp}
                                </span>
                              )}
                            </div>
                            {flag.quote && (
                              <p className="mt-1 text-xs italic text-muted">
                                «{flag.quote}»
                              </p>
                            )}
                          </div>
                        </button>
                      )
                    })}
                  </CardBody>
                </Card>
              )}

              {/* Natija signali */}
              {score.outcome_signal && (
                <Card>
                  <CardBody className="flex items-center gap-3 py-4">
                    <span className="icon-tile size-9 shrink-0 bg-good/10 text-good">
                      <Package className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-2xs uppercase tracking-wide text-muted">
                        {t('calls.outcome')}
                      </div>
                      {/* ⚠️ Xom qiymat («follow_up») ko'rsatilmaydi.
                          Bu — LLM javobidagi texnik kalit; ekranda uni
                          o'qigan odam nima demoqchiligini taxmin qilishga
                          majbur bo'lardi. Lug'atda yo'q yangi kalit
                          chiqsa `defaultValue` uni xom holda ko'rsatadi —
                          bo'sh joydan ko'ra shunisi yaxshi. */}
                      <div className="text-sm font-medium">
                        {t(`calls.outcomes.${score.outcome_signal.type}`, {
                          defaultValue: score.outcome_signal.type,
                        })}
                      </div>
                    </div>
                    <Badge>
                      <span className="tnum" title={t('calls.outcomeConfidence')}>
                        {Math.round(score.outcome_signal.confidence * 100)}%
                      </span>
                    </Badge>
                  </CardBody>
                </Card>
              )}

              {/* Koučing izohi */}
              {score.coaching_note && (
                <Card>
                  <CardBody className="flex gap-3 py-4">
                    <span className="icon-tile size-9 shrink-0 bg-warn/10 text-warn">
                      <Lightbulb className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <div className="text-2xs uppercase tracking-wide text-muted">
                        {t('calls.coaching')}
                      </div>
                      <p className="mt-1 text-sm leading-relaxed">
                        {score.coaching_note}
                      </p>
                    </div>
                  </CardBody>
                </Card>
              )}

              <p className="px-1 text-2xs text-muted">
                {t('calls.model')}: {score.model} · {t('nav.rubric')}{' '}
                {score.rubric_version}
              </p>
            </>
          ) : (
            /* ⚠️ Bahosi yo'q — SABABI aytilishi kerak.
               Ikki xil «bo'sh» bor va ular butunlay boshqa narsa:
                 · savdo bo'lmagan qo'ng'iroq — baholanMAYDI, hammasi
                   joyida, qayta yuborishning hojati yo'q;
                 · hali baholanmagan — navbatni kutyapti.
               Ilgari ikkalasida ham «Ma'lumot yo'q» yozilardi va menejer
               ichki suhbatni bejiz qayta baholashga yuborardi. */
            <Card>
              <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
                <span className="icon-tile size-10 bg-surface-2">
                  <ShieldQuestion className="size-5" />
                </span>
                {data.call_type && data.call_type !== 'sales' ? (
                  <>
                    <CallTypeBadge type={data.call_type} />
                    <p className="max-w-[26ch] text-xs leading-relaxed text-muted">
                      {t('calls.type.notScored')}
                    </p>
                    {data.call_type_reason && (
                      <p className="max-w-[30ch] text-2xs leading-relaxed text-muted">
                        «{data.call_type_reason}»
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted">{t('common.noData')}</p>
                )}
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </Page>
  )
}
