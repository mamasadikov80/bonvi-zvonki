/**
 * So'rovnoma sahifasi — Telegram Mini App.
 *
 * Marshrut: `/s`. Butun mahsulotdagi YAGONA ekran, uni xodim emas,
 * MIJOZ (do'kondor) ko'radi. Shuning uchun:
 *   • login yo'q, `AppShell` yo'q, sidebar yo'q — router'da `Gate` dan tashqarida
 *   • matnlar oddiy o'zbekcha, ichki atamalar («CSAT», «red flag») yo'q
 *   • ranglar Telegram mavzusidan olinadi, admin panelnikidan emas
 *
 * Autentifikatsiya — `Telegram.WebApp.initData` imzosi. Token ham
 * o'sha imzolangan matn ichida (`start_param`), URL'dan olinmaydi.
 */

import {
  AlertCircle,
  Check,
  Clock,
  Link2Off,
  Loader2,
  Lock,
  MessageCircle,
  ShieldCheck,
  WifiOff,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  openSurvey,
  submitSurvey,
  SurveyWebAppError,
  type FailureReason,
  type WebAppOpenResponse,
} from './api'
import {
  GhostButton,
  OptionList,
  PrimaryButton,
  Section,
  SectionTitle,
  StarRating,
  StatusScreen,
} from './components'
import { getWebApp, haptic, useTelegram } from './telegram'

import { MONTHS_UZ } from '@/shared/lib/date'
import { cn } from '@/shared/lib/utils'

/** Izoh uzunligi. Backend 2000 gacha ruxsat beradi — bu yerda ataylab
 *  kamroq: telefon klaviaturasida uzun matn yozilmaydi, hisoblagich esa
 *  chegara real bo'lgandagina ma'noli. */
const COMMENT_MAX = 500

/** Rahmat ekrani qancha turadi — o'qishga ulguradigan, lekin kutdirmaydigan */
const CLOSE_DELAY_MS = 2400

/**
 * «28 iyul – 10 avgust». Oy nomlari qo'lda yozilgan ro'yxatdan olinadi:
 * Chrome `toLocaleDateString('uz-UZ')` da oyni «M07» deb qaytaradi.
 * Sana har uch tilda ham o'zbekcha — bu sahifani do'kondor ko'radi.
 */
function formatPeriod(start: string, end: string): string {
  const from = new Date(start)
  const to = new Date(end)
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return ''

  const month = (d: Date) => MONTHS_UZ[d.getMonth()] ?? ''
  const sameMonth =
    from.getMonth() === to.getMonth() && from.getFullYear() === to.getFullYear()

  const tail = to.getFullYear() === new Date().getFullYear() ? '' : ` ${to.getFullYear()}`
  return sameMonth
    ? `${from.getDate()} – ${to.getDate()} ${month(to)}${tail}`
    : `${from.getDate()} ${month(from)} – ${to.getDate()} ${month(to)}${tail}`
}

function reasonOf(error: unknown): FailureReason {
  return error instanceof SurveyWebAppError ? error.reason : 'server'
}

const ERROR_ICON: Record<FailureReason, React.ReactNode> = {
  unauthorized: <Lock className="size-8" strokeWidth={1.75} />,
  notFound: <Link2Off className="size-8" strokeWidth={1.75} />,
  expired: <Clock className="size-8" strokeWidth={1.75} />,
  alreadyRated: <Check className="size-8" strokeWidth={2} />,
  invalid: <AlertCircle className="size-8" strokeWidth={1.75} />,
  unavailable: <AlertCircle className="size-8" strokeWidth={1.75} />,
  network: <WifiOff className="size-8" strokeWidth={1.75} />,
  server: <AlertCircle className="size-8" strokeWidth={1.75} />,
}

/** Qayta urinish faqat vaqtinchalik nosozliklarda ma'noli */
const RETRYABLE: FailureReason[] = ['network', 'server', 'unavailable']

type Phase = 'loading' | 'form' | 'already' | 'failed' | 'done'

export function SurveyWebAppPage() {
  /* Sahifa DOIM o'zbekcha — brauzer tilidan qat'i nazar.
     `useTranslation()` ning oddiy `t` si `navigator.language` ga qaraydi:
     telefoni ruscha bo'lgan do'kondorga ruscha, inglizchada esa inglizcha
     matn chiqardi. Bu sahifani faqat O'zbekistondagi do'kondor ko'radi va
     bot ham unga o'zbekcha yozadi — ikki xil tilda gapirmaslik kerak.
     Boshqa uch tildagi kalitlar loyiha izchilligi uchun saqlanadi. */
  const { i18n: instance } = useTranslation()
  const t = useMemo(() => instance.getFixedT('uz'), [instance])
  const tg = useTelegram()

  const [phase, setPhase] = useState<Phase>('loading')
  const [failure, setFailure] = useState<FailureReason>('server')
  const [survey, setSurvey] = useState<WebAppOpenResponse | null>(null)

  const [csat, setCsat] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [flags, setFlags] = useState<string[]>([])

  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<FailureReason | null>(null)

  const closeTimer = useRef<number | null>(null)

  const load = useCallback(async () => {
    setPhase('loading')
    try {
      const data = await openSurvey(tg.initData)
      setSurvey(data)
      setPhase(data.already_rated ? 'already' : 'form')
    } catch (error) {
      const reason = reasonOf(error)
      if (reason === 'alreadyRated') {
        setPhase('already')
        return
      }
      setFailure(reason)
      setPhase('failed')
    }
  }, [tg.initData])

  // Telegram tashqarisida so'rov umuman yuborilmaydi — imzo yo'q, javob 401
  useEffect(() => {
    if (!tg.available || !tg.initData) return
    void load()
  }, [tg.available, tg.initData, load])

  useEffect(() => {
    return () => {
      if (closeTimer.current) window.clearTimeout(closeTimer.current)
    }
  }, [])

  function pickCsat(value: number) {
    setCsat(value)
    setSendError(null)
    haptic('select')
  }

  function toggleFlag(key: string) {
    haptic('select')
    setFlags((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    )
  }

  async function send() {
    if (csat === null || sending) return
    setSending(true)
    setSendError(null)
    try {
      const trimmed = comment.trim()
      await submitSurvey(tg.initData, {
        csat,
        comment: trimmed.length > 0 ? trimmed : null,
        red_flags: flags,
      })
      haptic('success')
      setPhase('done')
      closeTimer.current = window.setTimeout(() => {
        getWebApp()?.close()
      }, CLOSE_DELAY_MS)
    } catch (error) {
      const reason = reasonOf(error)
      haptic('error')
      // Takroriy baho — formani ushlab turishning ma'nosi yo'q
      if (reason === 'alreadyRated') setPhase('already')
      else setSendError(reason)
    } finally {
      setSending(false)
    }
  }

  function close() {
    getWebApp()?.close()
  }

  /* ── Ekranlar ─────────────────────────────────────────────── */

  let screen: React.ReactNode

  if (!tg.available || !tg.initData) {
    // Oddiy brauzerda ochilgan: buzuq forma emas, tushunarli yo'riqnoma
    screen = (
      <StatusScreen
        icon={<MessageCircle className="size-8" strokeWidth={1.75} />}
        title={t('surveyApp.outside.title')}
        text={t('surveyApp.outside.text')}
      />
    )
  } else if (phase === 'loading') {
    screen = (
      <div className="flex min-h-[80vh] flex-col items-center justify-center gap-3">
        <Loader2 className="size-7 animate-spin text-[var(--sv-hint)]" />
        <p className="text-[0.9375rem] text-[var(--sv-hint)]">
          {t('surveyApp.loading')}
        </p>
      </div>
    )
  } else if (phase === 'already') {
    screen = (
      <StatusScreen
        icon={<Check className="size-8" strokeWidth={2.5} />}
        tone="accent"
        title={t('surveyApp.already.title')}
        text={t('surveyApp.already.text')}
      >
        <GhostButton onClick={close}>{t('surveyApp.closeButton')}</GhostButton>
      </StatusScreen>
    )
  } else if (phase === 'done') {
    screen = (
      <StatusScreen
        icon={<Check className="size-8" strokeWidth={2.5} />}
        tone="accent"
        title={t('surveyApp.done.title')}
        text={t('surveyApp.done.text')}
      >
        <p className="text-center text-[0.8125rem] text-[var(--sv-hint)]">
          {t('surveyApp.done.closing')}
        </p>
      </StatusScreen>
    )
  } else if (phase === 'failed') {
    screen = (
      <StatusScreen
        icon={ERROR_ICON[failure]}
        tone={failure === 'expired' ? 'neutral' : 'danger'}
        title={t(`surveyApp.error.${failure}.title`)}
        text={t(`surveyApp.error.${failure}.text`)}
      >
        {RETRYABLE.includes(failure) ? (
          <PrimaryButton onClick={() => void load()}>
            {t('surveyApp.retry')}
          </PrimaryButton>
        ) : (
          <GhostButton onClick={close}>{t('surveyApp.closeButton')}</GhostButton>
        )}
      </StatusScreen>
    )
  } else if (survey) {
    const period = formatPeriod(survey.period_start, survey.period_end)
    const commentLeft = COMMENT_MAX - comment.length

    screen = (
      <div className="flex flex-col gap-4 pt-5">
        {/* Sarlavha + anonimlik va'dasi.
            Va'da mayda shrift bilan pastga yashirilmaydi: odam o'zi savdo
            qiladigan kishini tanqid qilmoqda, ishonmasa rost yozmaydi. */}
        <header className="animate-fade-up px-1">
          <h1 className="text-[1.5rem] font-semibold leading-tight text-[var(--sv-text)]">
            {t('surveyApp.title')}
          </h1>
          <p className="mt-1.5 text-[0.9375rem] leading-snug text-[var(--sv-hint)]">
            {t('surveyApp.subtitle')}
          </p>
        </header>

        <div className="flex animate-fade-up items-start gap-2.5 rounded-2xl bg-[rgb(var(--sv-accent-rgb)/0.10)] px-3.5 py-3">
          <ShieldCheck
            className="mt-px size-5 shrink-0 text-[var(--sv-accent)]"
            strokeWidth={2}
          />
          <p className="text-[0.875rem] font-medium leading-snug text-[var(--sv-text)]">
            {t('surveyApp.anonymous')}
          </p>
        </div>

        <Section className="animate-fade-up">
          <p className="text-[0.75rem] font-medium uppercase tracking-wide text-[var(--sv-hint)]">
            {t('surveyApp.servedBy')}
          </p>
          <p className="mt-1 text-[1.125rem] font-semibold text-[var(--sv-text)]">
            {survey.agent_name}
          </p>
          {period ? (
            <p className="mt-0.5 text-[0.875rem] text-[var(--sv-hint)]">
              {t('surveyApp.periodPrefix', { period })}
            </p>
          ) : null}
        </Section>

        <Section className="animate-fade-up">
          <SectionTitle
            title={t('surveyApp.rating.question')}
            hint={t('surveyApp.rating.hint')}
          />
          <StarRating
            value={csat}
            onChange={pickCsat}
            labels={{
              1: t('surveyApp.rating.1'),
              2: t('surveyApp.rating.2'),
              3: t('surveyApp.rating.3'),
              4: t('surveyApp.rating.4'),
              5: t('surveyApp.rating.5'),
            }}
          />
        </Section>

        {survey.red_flags.length > 0 ? (
          <Section className="animate-fade-up">
            <SectionTitle
              title={t('surveyApp.flags.question')}
              hint={t('surveyApp.flags.hint')}
            />
            {/* Yorliqlar serverdan — bu yerda ro'yxat saqlanmaydi */}
            <OptionList
              options={survey.red_flags}
              selected={flags}
              onToggle={toggleFlag}
            />
          </Section>
        ) : null}

        <Section className="animate-fade-up">
          <SectionTitle
            title={t('surveyApp.comment.question')}
            hint={t('surveyApp.comment.hint')}
          />
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value.slice(0, COMMENT_MAX))}
            rows={4}
            maxLength={COMMENT_MAX}
            placeholder={t('surveyApp.comment.placeholder')}
            className={cn(
              'w-full resize-none rounded-xl px-3.5 py-3 text-[1rem] leading-snug',
              'bg-[rgb(var(--sv-separator-rgb)/0.10)] text-[var(--sv-text)]',
              'placeholder:text-[rgb(var(--sv-hint-rgb)/0.8)]',
              'outline-none ring-1 ring-transparent transition-all duration-250 ease-ios',
              'focus:ring-[rgb(var(--sv-accent-rgb)/0.5)]',
            )}
          />
          <p
            className={cn(
              'mt-1.5 text-right text-[0.75rem] tabular-nums',
              commentLeft === 0 ? 'text-[var(--sv-danger)]' : 'text-[var(--sv-hint)]',
            )}
          >
            {t('surveyApp.comment.counter', { n: comment.length, max: COMMENT_MAX })}
          </p>
        </Section>

        {sendError ? (
          <div className="flex animate-fade-up items-start gap-2.5 rounded-2xl bg-[rgb(var(--sv-danger-rgb)/0.12)] px-3.5 py-3">
            <AlertCircle
              className="mt-px size-5 shrink-0 text-[var(--sv-danger)]"
              strokeWidth={2}
            />
            <div>
              <p className="text-[0.9375rem] font-medium leading-snug text-[var(--sv-text)]">
                {t(`surveyApp.error.${sendError}.title`)}
              </p>
              <p className="mt-0.5 text-[0.8125rem] leading-snug text-[var(--sv-hint)]">
                {t(`surveyApp.error.${sendError}.text`)}
              </p>
            </div>
          </div>
        ) : null}

        <div className="animate-fade-up pt-1">
          <PrimaryButton onClick={() => void send()} disabled={csat === null || sending}>
            {sending ? (
              <>
                <Loader2 className="size-5 animate-spin" />
                {t('surveyApp.submitting')}
              </>
            ) : (
              t('surveyApp.submit')
            )}
          </PrimaryButton>
          <p
            className={cn(
              'mt-2.5 min-h-[1.125rem] text-center text-[0.8125rem] text-[var(--sv-hint)]',
              'transition-opacity duration-250 ease-ios',
              csat === null ? 'opacity-100' : 'opacity-0',
            )}
          >
            {t('surveyApp.needRating')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div
      // Telegram mavzusi shu yerda CSS o'zgaruvchilariga aylanadi
      style={tg.vars as React.CSSProperties}
      className="min-h-screen w-full bg-[var(--sv-bg)] font-sans antialiased"
    >
      <div className="mx-auto w-full max-w-[30rem] px-4 pb-[calc(2.5rem+env(safe-area-inset-bottom))]">
        {screen}
      </div>
    </div>
  )
}
