/**
 * Qo'ng'iroq yozuvi pleeri.
 *
 * Audio BIZDA saqlanmaydi: «Play» bosilganda backend MoyZvonki'dan
 * oqimni ochadi va baytlarni to'g'ridan-to'g'ri brauzerga uzatadi.
 * Avtorizatsiya qanday hal qilingani — `audio.ts` boshidagi izohda.
 */

import {
  AlertTriangle,
  Headphones,
  MicOff,
  Pause,
  Play,
  PlugZap,
  RotateCcw,
  RotateCw,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/modules/auth/store'
import {
  callAudioUrl,
  fetchAudioAsObjectUrl,
  prepareAudioBridge,
  useCallAudioProbe,
  type AudioProblem,
} from '@/modules/calls/audio'
import { cn, formatDuration } from '@/shared/lib/utils'
import { Badge, Button, Card, CardBody, Segmented, Skeleton } from '@/shared/ui/primitives'

const RATES: number[] = [1, 1.5, 2]
const SKIP_SECONDS = 10

/* ── Tugash animatsiyasi ──────────────────────────────────────
   Yozuv tugagach chiziq bir zum TO'LIQ yashil bo'lib turadi, keyin
   asl holatiga qaytadi. Bu bezak emas: menejer o'nlab qo'ng'iroqni
   ketma-ket tinglaydi va «bu yozuvni oxirigacha eshitdimmi yoki
   o'rtasida boshqasiga o'tib ketdimmi?» degan savol doim turadi.
   To'liq yashil — «tugadi» degan bir lahzalik javob. */

/** Tugagach necha ms to'liq yashil turadi */
const FINISH_HOLD_MS = 900
/** Keyin nolga qaytish necha ms davom etadi (CSS bilan bir xil) */
const FINISH_REWIND_MS = 500

/**
 * `idle`      — odatdagi holat
 * `full`      — yozuv tugadi, chiziq to'liq yashil
 * `rewinding` — boshiga qaytmoqda (sekin animatsiya)
 */
type FinishPhase = 'idle' | 'full' | 'rewinding'

/** Timeline ustidagi qoidabuzarlik belgisi */
export interface AudioMark {
  seconds: number
  label: string
}

/* ══════════════════════════════════════════════════════════════
   Boshqaruvchi (controller)

   Sahifa ham pleerga buyruq beradi (transkript qatoriga bosilganda
   seek), ham undan holat oladi (qaysi qator hozir o'qilyapti).
   Shuning uchun holat hook'da yashaydi, pleer esa uni chizadi.
   ══════════════════════════════════════════════════════════════ */

/** `<audio>` elementiga biriktiriladigan hodisalar */
interface AudioEvents {
  onLoadedMetadata: () => void
  onTimeUpdate: () => void
  onPlay: () => void
  onPause: () => void
  onEnded: () => void
  onWaiting: () => void
  onPlaying: () => void
  onError: () => void
}

/** Manba: SW ko'prigi orqali oqim yoki zaxira `blob:` */
type Source = 'none' | 'stream' | 'blob'

export interface CallAudioController {
  ref: React.RefObject<HTMLAudioElement | null>
  events: AudioEvents
  /** Yozuv bilan bog'liq muammo. `null` — hammasi joyida,
   *  `undefined` — hali tekshirilmoqda */
  problem: AudioProblem | null | undefined
  loading: boolean
  /** Backend `Range` ni qo'llab-quvvatladimi (206 qaytardimi) */
  ranges: boolean
  source: Source
  connecting: boolean
  playing: boolean
  waiting: boolean
  failed: boolean
  failureMessage: string | null
  currentTime: number
  duration: number
  rate: number
  /** Tugash animatsiyasining bosqichi — chiziq shunga qarab chiziladi */
  finish: FinishPhase
  toggle: () => void
  seek: (seconds: number, options?: { play?: boolean }) => void
  skip: (delta: number) => void
  setRate: (rate: number) => void
  retry: () => void
  /** Sudrash paytida — faqat ko'rsatkichni suradi, seek qilmaydi */
  preview: (seconds: number) => void
}

export function useCallAudio(
  callId: string | undefined,
  fallbackDuration: number,
): CallAudioController {
  const ref = useRef<HTMLAudioElement | null>(null)
  const probe = useCallAudioProbe(callId)

  const [source, setSource] = useState<Source>('none')
  const [connecting, setConnecting] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const [failure, setFailure] = useState<{ message: string | null } | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(fallbackDuration)
  const [rate, setRateState] = useState(1)
  const [finish, setFinish] = useState<FinishPhase>('idle')

  // `blob:` manzil yaratilgan bo'lsa uni ozod qilish shart
  const objectUrl = useRef<string | null>(null)
  // Foydalanuvchi yuklanishdan oldin transkript qatoriga bossa
  const pendingSeek = useRef<number | null>(null)
  // Hodisa ishlovchilari eski `rate` ni ushlab qolmasin
  const rateRef = useRef(rate)
  rateRef.current = rate

  // Tugash animatsiyasining taymerlari
  const finishTimers = useRef<number[]>([])

  /** Animatsiyani darhol to'xtatadi — foydalanuvchi aralashsa. */
  const clearFinish = useCallback(() => {
    finishTimers.current.forEach(clearTimeout)
    finishTimers.current = []
    setFinish('idle')
  }, [])

  useEffect(() => {
    setDuration((current) => (current > 0 ? current : fallbackDuration))
  }, [fallbackDuration])

  // Boshqa qo'ng'iroqqa o'tilganda xotira va taymerlar tozalanadi.
  // Taymer qolib ketsa, u yo'q komponentda `setState` chaqirardi.
  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
      finishTimers.current.forEach(clearTimeout)
      finishTimers.current = []
    },
    [callId],
  )

  /** Manbani biriktiradi: avval SW ko'prigi, bo'lmasa `blob:` */
  const attach = useCallback(async (): Promise<HTMLAudioElement | null> => {
    const audio = ref.current
    if (!audio || !callId) return null
    if (source !== 'none' && audio.src) return audio

    setConnecting(true)
    setFailure(null)
    try {
      const bridged = await prepareAudioBridge()
      if (bridged) {
        audio.src = callAudioUrl(callId)
        setSource('stream')
      } else {
        const url = await fetchAudioAsObjectUrl(callId)
        objectUrl.current = url
        audio.src = url
        setSource('blob')
      }
      audio.playbackRate = rateRef.current
      return audio
    } catch (error) {
      setFailure({ message: error instanceof Error ? error.message : null })
      return null
    } finally {
      setConnecting(false)
    }
  }, [callId, source])

  const start = useCallback(
    async (seconds?: number) => {
      // Tugash animatsiyasi ketayotgan bo'lsa — u endi eskirdi.
      // (Yozuv oxirida turgan bo'lsa, `play()` o'zi boshiga qaytaradi.)
      clearFinish()
      const audio = await attach()
      if (!audio || !audio.src) return

      if (seconds != null) {
        if (audio.readyState > 0) audio.currentTime = seconds
        else pendingSeek.current = seconds
        setCurrentTime(seconds)
      }

      try {
        await audio.play()
      } catch {
        /* Foydalanuvchi tugmani o'zi bosgan — avtoplay bloklanmaydi.
           Manba ochilmasa xabarni `onError` beradi. */
      }
    },
    [attach, clearFinish],
  )

  const toggle = useCallback(() => {
    const audio = ref.current
    if (audio?.src && !audio.paused) {
      audio.pause()
      return
    }
    void start()
  }, [start])

  const seek = useCallback(
    (seconds: number, options?: { play?: boolean }) => {
      clearFinish()
      const limit = duration || fallbackDuration
      const target = Math.max(0, Math.min(seconds, limit))
      const audio = ref.current
      setCurrentTime(target)

      if (!audio?.src) {
        // Hali yuklanmagan: bosilgan joydan boshlab ijro etamiz
        if (options?.play === false) pendingSeek.current = target
        else void start(target)
        return
      }

      if (audio.readyState > 0) audio.currentTime = target
      else pendingSeek.current = target
      if (options?.play && audio.paused) void audio.play().catch(() => undefined)
    },
    [clearFinish, duration, fallbackDuration, start],
  )

  const skip = useCallback(
    (delta: number) => seek(currentTime + delta, { play: false }),
    [currentTime, seek],
  )

  /** Sudrash — animatsiya davomida ham darhol boshqaruvni beradi */
  const preview = useCallback(
    (seconds: number) => {
      clearFinish()
      setCurrentTime(seconds)
    },
    [clearFinish],
  )

  const setRate = useCallback((next: number) => {
    setRateState(next)
    const audio = ref.current
    if (audio) audio.playbackRate = next
  }, [])

  const retry = useCallback(() => {
    clearFinish()
    setFailure(null)
    setSource('none')
    const audio = ref.current
    if (audio) {
      audio.removeAttribute('src')
      audio.load()
    }
    if (objectUrl.current) {
      URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
    }
    void probe.refetch()
  }, [clearFinish, probe])

  const events: AudioEvents = {
    onLoadedMetadata: () => {
      const audio = ref.current
      if (!audio) return
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setDuration(audio.duration)
      }
      audio.playbackRate = rateRef.current
      if (pendingSeek.current != null) {
        audio.currentTime = pendingSeek.current
        pendingSeek.current = null
      }
    },
    onTimeUpdate: () => setCurrentTime(ref.current?.currentTime ?? 0),
    onPlay: () => {
      setPlaying(true)
      setFailure(null)
      clearFinish()
    },
    onPause: () => setPlaying(false),
    onEnded: () => {
      setPlaying(false)

      // 1) Chiziq to'liq yashil bo'lib turadi.
      //    Foiz `currentTime` dan emas, shu bosqichdan olinadi:
      //    `duration` metama'lumotdan bir necha yuz millisekundga
      //    farq qilishi mumkin va chiziq 99.6% da qotib qolardi —
      //    ya'ni «tugadi» belgisi aynan tugaganda ko'rinmasdi.
      setFinish('full')

      finishTimers.current.forEach(clearTimeout)
      finishTimers.current = [
        // 2) Boshiga qaytish — sekin, ko'rinadigan animatsiya bilan
        window.setTimeout(() => {
          setFinish('rewinding')
          setCurrentTime(0)
          const audio = ref.current
          if (audio && audio.readyState > 0) audio.currentTime = 0
        }, FINISH_HOLD_MS),
        // 3) Asl holat
        window.setTimeout(
          () => setFinish('idle'),
          FINISH_HOLD_MS + FINISH_REWIND_MS,
        ),
      ]
    },
    onWaiting: () => setWaiting(true),
    onPlaying: () => setWaiting(false),
    onError: () => {
      setPlaying(false)
      setWaiting(false)
      setSource('none')
      setFailure({ message: null })
    },
  }

  const data = probe.data

  return {
    ref,
    events,
    problem: data === undefined ? undefined : data.ok ? null : data,
    loading: probe.isLoading,
    ranges: data?.ok ? data.ranges : false,
    source,
    connecting,
    playing,
    waiting,
    failed: failure !== null,
    failureMessage: failure?.message ?? null,
    currentTime,
    duration: duration || fallbackDuration,
    rate,
    finish,
    toggle,
    seek,
    skip,
    setRate,
    retry,
    preview,
  }
}

/* ── Xatolik ko'rinishi ────────────────────────────────────────
   MUHIM: sozlanmagan tizim BUZILGANDEK ko'rinmasligi kerak. Hozir
   MoyZvonki ulanmagan — bu nosozlik emas, shunchaki navbatdagi ish.
   Shuning uchun 404 va 503 xotirjam, kulrang izoh bilan chiqadi;
   ogohlantirish rangi faqat haqiqiy nosozlikda (502). */

function problemView(problem: AudioProblem): {
  warn: boolean
  icon: typeof MicOff
  titleKey: string
  action: 'settings' | 'retry' | null
} {
  switch (problem.code) {
    case 'recording_not_found':
      return { warn: false, icon: MicOff, titleKey: 'calls.audio.none', action: null }
    case 'moizvonki_not_configured':
      return {
        warn: false,
        icon: PlugZap,
        titleKey: 'calls.audio.notConfigured',
        action: 'settings',
      }
    case 'forbidden':
      return { warn: false, icon: MicOff, titleKey: 'calls.audio.forbidden', action: null }
    default:
      return {
        warn: true,
        icon: AlertTriangle,
        titleKey: 'calls.audio.unreachable',
        action: 'retry',
      }
  }
}

function ProblemPanel({
  problem,
  onRetry,
}: {
  problem: AudioProblem
  onRetry: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const can = useAuth((state) => state.can)
  const view = problemView(problem)
  const Icon = view.icon

  return (
    <div className="flex items-center gap-4">
      <span
        className={cn(
          'icon-tile size-10 shrink-0',
          view.warn ? 'bg-warn/10 text-warn' : 'bg-surface-2 text-muted',
        )}
      >
        <Icon className="size-4" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{t(view.titleKey)}</div>
        {/* Backendning o'zbekcha izohi — o'zgartirilmaydi */}
        <p className="mt-0.5 text-xs leading-relaxed text-muted">{problem.message}</p>
      </div>

      {view.action === 'settings' && can('settings:read') && (
        <Button
          variant="secondary"
          size="sm"
          className="shrink-0"
          onClick={() => navigate('/settings')}
        >
          {t('calls.audio.openSettings')}
        </Button>
      )}
      {view.action === 'retry' && (
        <Button variant="secondary" size="sm" className="shrink-0" onClick={onRetry}>
          {t('common.retry')}
        </Button>
      )}
    </div>
  )
}

/* ── Sudraladigan vaqt chizig'i ─────────────────────────────────

   Ko'rinadigan chiziq INGICHKA (12px), bosiladigan maydon esa baland
   (36px) — ya'ni ko'rinishi pleernikidek, mo'ljali esa avvalgidek
   keng. Ilgari ikkalasi bir xil edi va 36px lik kulrang to'rtburchak
   pleer chizig'iga emas, bo'sh kiritish maydoniga o'xshab turardi.

   Dumaloq nuqta (thumb) YO'Q. U sudrash uchun kerak emas — bosilgan
   joyning o'zi pozitsiyani beradi — lekin 0:00 da chiziq boshida
   ma'nosiz nuqta bo'lib osilib turardi. Endi joriy holatni to'lgan
   qismning o'ng cheti ko'rsatadi. */

function Scrubber({
  value,
  max,
  marks,
  finish,
  onPreview,
  onCommit,
  label,
}: {
  value: number
  max: number
  marks: AudioMark[]
  finish: FinishPhase
  onPreview: (seconds: number) => void
  onCommit: (seconds: number) => void
  label: string
}) {
  const track = useRef<HTMLDivElement | null>(null)
  const [dragging, setDragging] = useState(false)

  const secondsAt = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return 0
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * max
  }

  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  // Tugagan lahzada chiziq TO'LIQ yashil bo'lishi kerak, `duration`
  // metama'lumotdagi bir necha yuz millisekundlik farqdan qat'i nazar
  const filled = finish === 'full' ? 100 : percent

  return (
    <div
      ref={track}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={Math.round(max)}
      aria-valuenow={Math.round(value)}
      aria-valuetext={formatDuration(Math.round(value))}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId)
        setDragging(true)
        onPreview(secondsAt(event.clientX))
      }}
      onPointerMove={(event) => {
        if (dragging) onPreview(secondsAt(event.clientX))
      }}
      onPointerUp={(event) => {
        if (!dragging) return
        setDragging(false)
        onCommit(secondsAt(event.clientX))
      }}
      onPointerCancel={() => setDragging(false)}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 30 : 5
        if (event.key === 'ArrowRight') {
          event.preventDefault()
          onCommit(Math.min(max, value + step))
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault()
          onCommit(Math.max(0, value - step))
        }
      }}
      className={cn(
        'group relative flex h-9 cursor-pointer touch-none select-none items-center',
        'focus-visible:outline-none',
      )}
    >
      {/* Chiziq */}
      <div
        className={cn(
          'relative w-full overflow-hidden rounded-full bg-surface-2',
          // Sudrash paytida sal qalinlashadi — barmoq ostida
          // «ushladim» degan javob bo'ladi
          'transition-[height] duration-250 ease-ios',
          dragging ? 'h-3.5' : 'h-3',
          'group-focus-visible:ring-2 group-focus-visible:ring-accent/40',
        )}
      >
        {/* Eshitilgan qism */}
        <div
          className={cn(
            'absolute inset-y-0 left-0 rounded-full bg-good',
            // Sudrashda animatsiya YO'Q: chiziq barmoqdan orqada
            // qolsa, boshqaruv «og'ir» bo'lib tuyuladi.
            // Tugagach esa qasddan sekin — qaytish ko'rinsin.
            dragging
              ? undefined
              : finish === 'idle'
                ? 'transition-[width] duration-150 ease-linear'
                : 'transition-[width] duration-500 ease-ios',
          )}
          style={{ width: `${filled}%` }}
        />

        {/* Qoidabuzarlik belgilari — to'lgan qismning USTIDA */}
        {marks.map((mark, index) => (
          <span
            key={index}
            title={mark.label}
            className="pointer-events-none absolute inset-y-0 w-[3px] rounded-full bg-bad"
            style={{
              left: `${max > 0 ? Math.min(99.5, (mark.seconds / max) * 100) : 0}%`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

/* ── Pleer ───────────────────────────────────────────────────── */

export function CallAudioPlayer({
  controller,
  marks,
}: {
  controller: CallAudioController
  marks: AudioMark[]
}) {
  const { t } = useTranslation()
  const {
    problem,
    loading,
    playing,
    connecting,
    waiting,
    failed,
    failureMessage,
    currentTime,
    duration,
    rate,
    finish,
    source,
    ranges,
  } = controller

  // Tugagani chiziqdan ham ko'rinadi, lekin matn bilan birga u
  // ANIQ bo'ladi: «to'liq eshitildi» — menejer uchun bu qayd
  const finished = finish !== 'idle'

  const status = failed
    ? failureMessage || t('calls.audio.failed')
    : finished
      ? t('calls.audio.finished')
      : connecting
        ? t('calls.audio.connecting')
        : waiting
          ? t('calls.audio.buffering')
          : source === 'stream'
            ? t(ranges ? 'calls.audio.streaming' : 'calls.audio.stream')
            : source === 'blob'
              ? t('calls.audio.buffered')
              : t('calls.audio.hint')

  return (
    <Card>
      <CardBody className="py-4">
        {/* Element doim turadi: holat o'zgarganda qayta yaratilsa,
            ochilgan oqim uzilib qolardi */}
        <audio ref={controller.ref} preload="none" className="hidden" {...controller.events} />

        {loading ? (
          <div className="flex items-center gap-4">
            <Skeleton className="size-11 rounded-full" />
            <div className="flex-1">
              {/* Skelet haqiqiy chiziqning o'lchamini takrorlaydi:
                  yuklanib bo'lgach sahifa sakramasin */}
              <div className="flex h-9 items-center">
                <Skeleton className="h-3 w-full rounded-full" />
              </div>
              <Skeleton className="mt-1.5 h-3 w-28" />
            </div>
          </div>
        ) : problem ? (
          <ProblemPanel problem={problem} onRetry={controller.retry} />
        ) : (
          <>
            <div className="flex items-center gap-4">
              {/* Play / Pause */}
              <button
                type="button"
                onClick={controller.toggle}
                aria-label={playing ? t('calls.audio.pause') : t('calls.audio.play')}
                className={cn(
                  'grid size-11 shrink-0 place-items-center rounded-full',
                  'bg-accent text-white shadow-soft',
                  'transition-all duration-250 ease-ios hover:bg-accent/90 active:scale-[0.94]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
                )}
              >
                {playing ? (
                  <Pause className="size-5" />
                ) : (
                  <Play className="size-5 translate-x-[1px]" />
                )}
              </button>

              <div className="min-w-0 flex-1">
                <Scrubber
                  label={t('calls.audio.scrub')}
                  value={currentTime}
                  max={duration}
                  marks={marks}
                  finish={finish}
                  onPreview={controller.preview}
                  onCommit={(seconds) => controller.seek(seconds, { play: playing })}
                />

                <div className="mt-1.5 flex items-center justify-between gap-3 text-2xs text-muted">
                  <span className="tnum shrink-0">
                    {formatDuration(Math.floor(currentTime))}
                    <span className="mx-1 opacity-50">/</span>
                    {formatDuration(Math.round(duration))}
                  </span>
                  <span
                    className={cn(
                      'truncate transition-colors duration-250',
                      failed && 'text-warn',
                      !failed && finished && 'font-medium text-good',
                    )}
                  >
                    {status}
                  </span>
                </div>
              </div>

              {/* ±10 soniya */}
              <div className="hidden shrink-0 items-center gap-1 sm:flex">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('calls.audio.back10')}
                  onClick={() => controller.skip(-SKIP_SECONDS)}
                >
                  <RotateCcw className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('calls.audio.forward10')}
                  onClick={() => controller.skip(SKIP_SECONDS)}
                >
                  <RotateCw className="size-4" />
                </Button>
              </div>

              {/* Tezlik — 1.5× ko'p qo'ng'iroq tinglaydigan menejer uchun */}
              <Segmented
                className="shrink-0"
                value={rate}
                onChange={controller.setRate}
                items={RATES.map((value) => ({ value, label: `${value}×` }))}
              />
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-2xs text-muted">
              <Headphones className="size-3 shrink-0" />
              <span>{t('calls.audio.source')}</span>
              {source === 'blob' && <Badge>{t('calls.audio.noRangeMode')}</Badge>}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  )
}
