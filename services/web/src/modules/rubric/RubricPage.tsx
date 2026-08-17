import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  History,
  Info,
  Lock,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuth } from '@/modules/auth/store'
import { api, ApiError } from '@/shared/api/client'
import { Page, PageGrid, PageHeader } from '@/shared/layout/Page'
import { formatFullDate } from '@/shared/lib/date'
import { cn, formatNumber } from '@/shared/lib/utils'
import { Modal, ModalFields } from '@/shared/ui/Modal'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Input,
  Label,
  Skeleton,
} from '@/shared/ui/primitives'

/* ── Turlar ──────────────────────────────────────────────── */

interface Criterion {
  id: string
  label: string
  points: number
  description?: string | null
}

interface Block {
  key: string
  label: string
  max: number
  criteria: Criterion[]
}

interface RedFlag {
  type: string
  label: string
  penalty: number
  zeroes_score: boolean
  description?: string | null
}

interface Rubric {
  id: string
  version: number
  name: string
  description: string | null
  is_active: boolean
  blocks: Block[]
  red_flags: RedFlag[]
  extra_rules: string | null
  created_at: string
}

/** AI ga yuboriladigan tizim promptining bo'laklari.
 *  Faqat bittasi tahrirlanadi; qolganlari ko'rinadi-yu, o'zgarmaydi. */
interface PromptSection {
  key: string
  editable: boolean
  text: string
}

interface PromptPreview {
  rubric_version: number
  sections: PromptSection[]
  full_text: string
  char_count: number
  approx_tokens: number
  extra_rules_limit: number
}

/** Qo'shimcha qoidalar uchun chegara — backenddagi `MAX_EXTRA_RULES`
 *  bilan bir xil. Matn har qo'ng'iroqda AI ga yuboriladi, ya'ni
 *  uzunligi pulga aylanadi. */
const EXTRA_LIMIT = 4000

/** Red flag kalitining ruxsat etilgan shakli — backend validatsiyasi
 *  bilan AYNAN bir xil (`RED_FLAG_KEY`).
 *
 *  Nega frontendda ham tekshiriladi: kalit noto'g'ri bo'lsa saqlash
 *  422 bilan qaytadi va admin butun formani qaytadan to'ldiradi.
 *  Darhol ko'rsatilgan xato — bir necha daqiqalik ishni tejaydi. */
const FLAG_KEY = /^[a-z][a-z0-9_]{1,31}$/

/** Yorliqni kalitga aylantiradi — admin kalitni O'ZI yozmasligi kerak.
 *
 *  Kalit texnik narsa (promptga va JSON sxemasiga tushadi), admin esa
 *  «Mijozni shaxsiy raqamga o'g'dirish» deb o'ylaydi. Uni qo'lda
 *  yozdirish keraksiz xato manbai bo'lardi. */
function slugify(label: string): string {
  const map: Record<string, string> = {
    'ʻ': '', "'": '', '‘': '', '’': '', 'ў': 'o', 'қ': 'q', 'ғ': 'g', 'ҳ': 'h',
  }
  return label
    .toLowerCase()
    .split('')
    .map((ch) => map[ch] ?? ch)
    .join('')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 32)
}

/** Tahrirlanayotgan nishon */
type Target =
  | { kind: 'criterion'; blockIndex: number; index: number }
  | { kind: 'newCriterion'; blockIndex: number }
  | { kind: 'block'; index: number }
  | { kind: 'flag'; index: number }
  | { kind: 'newFlag' }
  | null

/* ── Sahifa ──────────────────────────────────────────────── */

export function RubricPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const queryClient = useQueryClient()

  const canEdit = can('rubric:write')
  const [blocks, setBlocks] = useState<Block[] | null>(null)
  const [flags, setFlags] = useState<RedFlag[] | null>(null)
  /* Adminning qo'shimcha ko'rsatmalari. `null` — hali yuklanmagan
     (bo'sh satrdan farqli: bo'sh satr «ko'rsatma yo'q» degani). */
  const [extraRules, setExtraRules] = useState<string | null>(null)
  const [promptOpen, setPromptOpen] = useState(false)
  const [target, setTarget] = useState<Target>(null)
  const [error, setError] = useState<string | null>(null)

  const rubric = useQuery({
    queryKey: ['rubric'],
    queryFn: () => api.get<Rubric>('/rubric'),
  })

  const versions = useQuery({
    queryKey: ['rubric', 'versions'],
    queryFn: () =>
      api.get<{ version: number; name: string; is_active: boolean; created_at: string }[]>(
        '/rubric/versions',
      ),
  })

  useEffect(() => {
    if (rubric.data) {
      setBlocks(rubric.data.blocks)
      setFlags(rubric.data.red_flags)
      setExtraRules(rubric.data.extra_rules ?? '')
    }
  }, [rubric.data])

  const save = useMutation({
    mutationFn: () =>
      api.put<Rubric>('/rubric', {
        blocks,
        red_flags: flags,
        // Bo'sh satr `null` ga aylanadi — bo'sh maydon promptda bo'sh
        // sarlavha qoldirmasligi kerak
        extra_rules: (extraRules ?? '').trim() || null,
      }),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['rubric'] })
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : 'Xatolik'),
  })

  if (rubric.isLoading || !blocks || !flags || extraRules === null) {
    return (
      <Page>
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64 w-full" />
      </Page>
    )
  }

  const total = blocks.reduce((sum, b) => sum + b.max, 0)
  const balanced = total === 100
  const dirty =
    JSON.stringify({ blocks, flags, extraRules: extraRules.trim() }) !==
    JSON.stringify({
      blocks: rubric.data?.blocks,
      flags: rubric.data?.red_flags,
      extraRules: (rubric.data?.extra_rules ?? '').trim(),
    })

  return (
    <Page>
      <PageHeader
        title={t('nav.rubric')}
        subtitle={t('rubric.subtitle')}
        actions={
          <>
            <Badge tone="accent">
              <History className="size-3" />v{rubric.data?.version}
            </Badge>
            {canEdit ? (
              <Button
                disabled={!dirty || !balanced || save.isPending}
                onClick={() => save.mutate()}
              >
                {save.isPending ? t('settings.saving') : t('rubric.saveVersion')}
              </Button>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                <Lock className="size-3.5" />
                {t('settings.adminOnly')}
              </span>
            )}
          </>
        }
      />

      {/* Ball balansi */}
      <div className={cn('card flex items-center gap-3 p-4', !balanced && 'ring-1 ring-bad/40')}>
        <span
          className={cn(
            'icon-tile size-9',
            balanced ? 'bg-good/10 text-good' : 'bg-bad/10 text-bad',
          )}
        >
          {balanced ? <Info className="size-4" /> : <AlertTriangle className="size-4" />}
        </span>
        <div className="flex-1">
          <div className="text-sm font-medium">
            {t('rubric.total')}: <span className="tnum">{total}</span> / 100
          </div>
          <p className="text-xs text-muted">
            {balanced ? t('rubric.balanced') : t('rubric.unbalanced')}
          </p>
        </div>
      </div>

      {error && (
        <div className="card animate-scale-in bg-bad/5 p-4 text-sm text-bad ring-1 ring-bad/30">
          {error}
        </div>
      )}

      {/* Bloklar — faqat KO'RSATISH, tahrir modal orqali */}
      <PageGrid>
        {blocks.map((block, bi) => {
          const sum = block.criteria.reduce((s, c) => s + c.points, 0)
          const ok = sum === block.max
          return (
            <Card key={block.key}>
              <CardHeader
                title={block.label}
                hint={t('rubric.blockHint', { sum, max: block.max })}
                action={
                  <div className="flex items-center gap-2">
                    <Badge tone={ok ? 'good' : 'bad'}>
                      <span className="tnum">
                        {sum}/{block.max}
                      </span>
                    </Badge>
                    {canEdit && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        title={t('common.edit')}
                        onClick={() => setTarget({ kind: 'block', index: bi })}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                    )}
                  </div>
                }
              />
              <CardBody className="space-y-1.5 pt-3">
                {block.criteria.map((criterion, ci) => (
                  <button
                    key={criterion.id}
                    disabled={!canEdit}
                    onClick={() =>
                      setTarget({ kind: 'criterion', blockIndex: bi, index: ci })
                    }
                    className={cn(
                      'flex w-full items-start gap-3 rounded-xl bg-surface-2/60 p-3 text-left',
                      canEdit &&
                        'transition-all duration-250 ease-ios hover:bg-surface-2 active:scale-[0.99]',
                    )}
                  >
                    <Badge className="mt-0.5 shrink-0 font-mono">{criterion.id}</Badge>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{criterion.label}</div>
                      {criterion.description && (
                        <p className="mt-0.5 text-xs text-muted">
                          {criterion.description}
                        </p>
                      )}
                    </div>
                    <span className="tnum shrink-0 text-sm font-semibold">
                      {criterion.points}
                    </span>
                    {canEdit && <Pencil className="mt-1 size-3 shrink-0 text-muted" />}
                  </button>
                ))}

                {canEdit && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full"
                    onClick={() => setTarget({ kind: 'newCriterion', blockIndex: bi })}
                  >
                    <Plus className="size-3.5" />
                    {t('rubric.addCriterion')}
                  </Button>
                )}
              </CardBody>
            </Card>
          )
        })}
      </PageGrid>

      {/* Red flag'lar */}
      <Card>
        <CardHeader title={t('rubric.redFlags')} hint={t('rubric.redFlagsHint')} />
        <CardBody className="grid gap-1.5 pt-3 xl:grid-cols-2">
          {flags.map((flag, i) => (
            <button
              key={flag.type}
              disabled={!canEdit || flag.zeroes_score}
              onClick={() => setTarget({ kind: 'flag', index: i })}
              className={cn(
                'flex w-full items-center gap-3 rounded-xl bg-surface-2/60 p-3 text-left',
                canEdit &&
                  !flag.zeroes_score &&
                  'transition-all duration-250 ease-ios hover:bg-surface-2 active:scale-[0.99]',
              )}
            >
              <span className="icon-tile size-8 shrink-0 bg-bad/10 text-bad">
                <AlertTriangle className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{flag.label}</div>
                {flag.description && (
                  <p className="mt-0.5 text-xs text-muted">{flag.description}</p>
                )}
              </div>
              {flag.zeroes_score ? (
                <Badge tone="bad">{t('rubric.zeroesScore')}</Badge>
              ) : (
                <span className="tnum shrink-0 text-sm font-semibold text-bad">
                  {flag.penalty}
                </span>
              )}
            </button>
          ))}
          {canEdit && (
            <Button
              variant="ghost"
              className="justify-start"
              onClick={() => setTarget({ kind: 'newFlag' })}
            >
              <Plus className="size-3.5" />
              {t('rubric.addFlag')}
            </Button>
          )}
        </CardBody>
      </Card>

      {/* ── Qo'shimcha qoidalar ────────────────────────────── */}
      <Card>
        <CardHeader
          title={t('rubric.extraRules')}
          hint={t('rubric.extraRulesHint')}
        />
        <CardBody className="pt-3">
          {canEdit ? (
            <>
              <textarea
                value={extraRules}
                onChange={(e) => setExtraRules(e.target.value.slice(0, EXTRA_LIMIT))}
                rows={8}
                placeholder={t('rubric.extraRulesPlaceholder')}
                className={cn(
                  'w-full resize-y rounded-xl bg-surface-2 px-3.5 py-3 text-xs leading-relaxed',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
                )}
              />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                {/* Uzunlik PULGA bog'liq: bu matn har bir qo'ng'iroqda
                    AI ga yuboriladi, shuning uchun hisoblagich ko'rinadi */}
                <p className="text-2xs text-muted">
                  {t('rubric.extraRulesCount', {
                    count: extraRules.length,
                    limit: EXTRA_LIMIT,
                  })}
                </p>
                <button
                  onClick={() => setPromptOpen((v) => !v)}
                  className="text-2xs font-medium text-accent hover:underline"
                >
                  {promptOpen ? t('rubric.promptHide') : t('rubric.promptShow')}
                </button>
              </div>
            </>
          ) : (
            <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted">
              {extraRules || t('rubric.extraRulesEmpty')}
            </p>
          )}
        </CardBody>
      </Card>

      {/* ── AI ga yuboriladigan so'rov (o'qish uchun) ──────── */}
      {promptOpen && <PromptView />}

      {/* Versiyalar tarixi */}
      {versions.data && versions.data.length > 1 && (
        <Card>
          <CardHeader title={t('rubric.history')} hint={t('rubric.historyHint')} />
          <CardBody className="grid gap-1.5 pt-3 xl:grid-cols-2">
            {versions.data.map((v) => (
              <div
                key={v.version}
                className="flex items-center gap-3 rounded-xl bg-surface-2/60 px-3 py-2.5"
              >
                <Badge tone={v.is_active ? 'accent' : 'neutral'} className="font-mono">
                  v{v.version}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-sm">{v.name}</span>
                <span className="text-2xs text-muted">
                  {formatFullDate(v.created_at)}
                </span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {/* ── Tahrirlash modallari ────────────────────────── */}
      <EditModal
        target={target}
        blocks={blocks}
        flags={flags}
        onClose={() => setTarget(null)}
        onApply={(nextBlocks, nextFlags) => {
          if (nextBlocks) setBlocks(nextBlocks)
          if (nextFlags) setFlags(nextFlags)
          setTarget(null)
        }}
      />
    </Page>
  )
}

/* ── Universal tahrir modali ─────────────────────────────── */

function EditModal({
  target,
  blocks,
  flags,
  onClose,
  onApply,
}: {
  target: Target
  blocks: Block[]
  flags: RedFlag[]
  onClose: () => void
  onApply: (blocks: Block[] | null, flags: RedFlag[] | null) => void
}) {
  const { t } = useTranslation()

  const [draft, setDraft] = useState<Record<string, string | number>>({})
  const [loadedKey, setLoadedKey] = useState<string | null>(null)

  const key = target ? JSON.stringify(target) : null
  if (key && key !== loadedKey) {
    setLoadedKey(key)
    if (target?.kind === 'criterion') {
      const c = blocks[target.blockIndex].criteria[target.index]
      setDraft({ id: c.id, label: c.label, points: c.points, description: c.description ?? '' })
    } else if (target?.kind === 'newCriterion') {
      const block = blocks[target.blockIndex]
      setDraft({
        id: `${block.key[0].toUpperCase()}${block.criteria.length + 1}`,
        label: '',
        points: 0,
        description: '',
      })
    } else if (target?.kind === 'block') {
      const b = blocks[target.index]
      setDraft({ label: b.label, max: b.max })
    } else if (target?.kind === 'flag') {
      const f = flags[target.index]
      setDraft({ label: f.label, penalty: f.penalty, description: f.description ?? '' })
    } else if (target?.kind === 'newFlag') {
      setDraft({ label: '', penalty: -10, description: '', type: '' })
    }
  }

  if (!target) {
    return (
      <Modal open={false} onOpenChange={onClose} title="">
        <div />
      </Modal>
    )
  }

  const titles: Record<string, string> = {
    criterion: t('rubric.editCriterion'),
    newCriterion: t('rubric.addCriterion'),
    block: t('rubric.editBlock'),
    flag: t('rubric.editFlag'),
    newFlag: t('rubric.addFlag'),
  }

  const apply = () => {
    if (target.kind === 'criterion' || target.kind === 'newCriterion') {
      const bi = target.blockIndex
      const criterion: Criterion = {
        id: String(draft.id).trim(),
        label: String(draft.label).trim(),
        points: Number(draft.points),
        description: String(draft.description).trim() || null,
      }
      const next = blocks.map((b, i) => {
        if (i !== bi) return b
        const criteria =
          target.kind === 'newCriterion'
            ? [...b.criteria, criterion]
            : b.criteria.map((c, j) => (j === target.index ? criterion : c))
        return { ...b, criteria }
      })
      onApply(next, null)
    } else if (target.kind === 'block') {
      const next = blocks.map((b, i) =>
        i === target.index
          ? { ...b, label: String(draft.label).trim(), max: Number(draft.max) }
          : b,
      )
      onApply(next, null)
    } else if (target.kind === 'newFlag') {
      onApply(null, [
        ...flags,
        {
          type: flagKey,
          label: String(draft.label).trim(),
          penalty: Number(draft.penalty),
          // Yangi red flag HECH QACHON ballni nolga tushirmaydi.
          // `zeroes_score` — eng og'ir chora (haqorat uchun) va uni
          // bir bosishda qo'shib qo'yish xavfli: bitta xato tasnif
          // xodimning bahosini nolga tushirardi. Kerak bo'lsa mavjud
          // qoidani tahrirlash yo'li bor.
          zeroes_score: false,
          description: String(draft.description).trim() || null,
        },
      ])
    } else if (target.kind === 'flag') {
      const next = flags.map((f, i) =>
        i === target.index
          ? {
              ...f,
              label: String(draft.label).trim(),
              penalty: Number(draft.penalty),
              description: String(draft.description).trim() || null,
            }
          : f,
      )
      onApply(null, next)
    }
  }

  const remove = () => {
    if (target.kind !== 'criterion') return
    const next = blocks.map((b, i) =>
      i === target.blockIndex
        ? { ...b, criteria: b.criteria.filter((_, j) => j !== target.index) }
        : b,
    )
    onApply(next, null)
  }

  const isCriterion = target.kind === 'criterion' || target.kind === 'newCriterion'
  const isFlag = target.kind === 'flag' || target.kind === 'newFlag'

  // Yangi red flag kaliti yorliqdan hosil qilinadi
  const flagKey = slugify(String(draft.label ?? ''))
  const flagKeyOk = FLAG_KEY.test(flagKey) && !flags.some((f) => f.type === flagKey)

  const valid =
    String(draft.label ?? '').trim().length >= 2 &&
    (target.kind !== 'newFlag' || flagKeyOk)

  return (
    <Modal
      open
      onOpenChange={(open) => !open && onClose()}
      title={titles[target.kind]}
      size="md"
      footer={
        <>
          {target.kind === 'criterion' && (
            <Button variant="ghost" className="mr-auto text-bad" onClick={remove}>
              <Trash2 className="size-4" />
              {t('common.delete')}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!valid} onClick={apply}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ModalFields columns={isCriterion ? 2 : 1}>
          {isCriterion && (
            <div>
              <Label>{t('rubric.criterionId')}</Label>
              <Input
                className="font-mono"
                value={String(draft.id ?? '')}
                onChange={(e) => setDraft({ ...draft, id: e.target.value })}
              />
            </div>
          )}

          <div className={cn(isCriterion && 'sm:col-span-1')}>
            <Label>{t('rubric.label')}</Label>
            <Input
              autoFocus
              value={String(draft.label ?? '')}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            />
          </div>
        </ModalFields>

        {isCriterion && (
          <div>
            <Label>{t('rubric.points')}</Label>
            <Input
              type="number"
              min={0}
              max={100}
              value={String(draft.points ?? 0)}
              onChange={(e) => setDraft({ ...draft, points: Number(e.target.value) })}
            />
          </div>
        )}

        {target.kind === 'block' && (
          <div>
            <Label>{t('rubric.blockMax')}</Label>
            <Input
              type="number"
              min={1}
              max={100}
              value={String(draft.max ?? 0)}
              onChange={(e) => setDraft({ ...draft, max: Number(e.target.value) })}
            />
          </div>
        )}

        {target.kind === 'newFlag' && (
          <div className="rounded-xl bg-surface-2/60 px-3.5 py-3">
            {/* Kalit AI ga yuboriladi va bazaga yoziladi — admin uni
                ko'rishi kerak, lekin qo'lda yozishi shart emas */}
            <Label className="mb-1">{t('rubric.flagKey')}</Label>
            <code className="text-xs">{flagKey || '—'}</code>
            {!flagKeyOk && flagKey && (
              <p className="mt-1.5 text-2xs leading-relaxed text-bad">
                {flags.some((f) => f.type === flagKey)
                  ? t('rubric.flagKeyDuplicate')
                  : t('rubric.flagKeyInvalid')}
              </p>
            )}
            <p className="mt-1.5 text-2xs leading-relaxed text-muted">
              {t('rubric.flagKeyHint')}
            </p>
          </div>
        )}

        {isFlag && (
          <div>
            <Label>{t('rubric.penalty')}</Label>
            <Input
              type="number"
              max={0}
              value={String(draft.penalty ?? 0)}
              onChange={(e) => setDraft({ ...draft, penalty: Number(e.target.value) })}
            />
            <p className="mt-1 text-2xs text-muted">{t('rubric.penaltyHint')}</p>
          </div>
        )}

        {(isCriterion || target.kind === 'flag') && (
          <div>
            <Label>{t('rubric.description')}</Label>
            <Input
              value={String(draft.description ?? '')}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </div>
        )}
      </div>
    </Modal>
  )
}

/* ── AI ga yuboriladigan so'rov (faqat o'qish) ────────────── */

/**
 * Tizim promptini bo'laklarga ajratib ko'rsatadi.
 *
 * NEGA BU KERAK. Admin baholashga ta'sir qiladigan matnni tahrirlaydi.
 * AI ga aynan nima ketayotganini ko'rmasa — ko'r-ko'rona ishlaydi:
 * allaqachon aytilgan qoidani takrorlaydi (tokenni bejiz to'laydi) yoki
 * unga zid gap yozib, nega natija o'zgarmaganini tushunmaydi.
 *
 * NEGA FAQAT O'QISH. Til qoidalari, ball hisoblash tartibi va JAVOB
 * SHAKLI o'zgarmas: ular buzilsa LLM javobi validatsiyadan o'tmaydi va
 * HAR BIR baho yiqiladi. Ya'ni bitta tahrir butun tizimni to'xtatardi.
 * Shuning uchun ular ko'rinadi, lekin tegib bo'lmaydi.
 *
 * ⚠️ Matn `GET /rubric/prompt` dan olinadi, frontendda QAYTA QURILMAYDI.
 * Bu yerda takrorlansa ikki nusxa vaqt o'tib ajralib ketardi: panelda
 * bir narsa ko'rinardi, AI ga boshqasi ketardi — hech qanday belgisi
 * bo'lmagan xato.
 */
function PromptView() {
  const { t } = useTranslation()
  const preview = useQuery({
    queryKey: ['rubric', 'prompt'],
    queryFn: () => api.get<PromptPreview>('/rubric/prompt'),
  })

  if (preview.isLoading) {
    return (
      <Card>
        <CardBody>
          <Skeleton className="h-48 w-full" />
        </CardBody>
      </Card>
    )
  }
  if (!preview.data) return null

  const { sections, char_count, approx_tokens } = preview.data

  return (
    <Card>
      <CardHeader
        title={t('rubric.promptTitle')}
        hint={t('rubric.promptHint')}
        action={
          <Badge tone="neutral" className="font-mono">
            {formatNumber(char_count)} · ~{formatNumber(approx_tokens)} tok
          </Badge>
        }
      />
      <CardBody className="space-y-2 pt-3">
        {sections
          // Bo'sh bo'lim ko'rsatilmaydi: qoida yozilmagan bo'lsa bo'sh
          // ramka «nimadir yo'qolgan» degan taassurot berardi
          .filter((section) => section.text.trim())
          .map((section) => (
            <div
              key={section.key}
              className={cn(
                'rounded-xl p-3',
                section.editable
                  ? 'bg-accent-soft ring-1 ring-accent/20'
                  : 'bg-surface-2/60',
              )}
            >
              <div className="mb-1.5 flex items-center gap-2">
                {section.editable ? (
                  <Badge tone="accent">
                    <Pencil className="size-3" />
                    {t('rubric.promptEditable')}
                  </Badge>
                ) : (
                  <Badge tone="neutral">
                    <Lock className="size-3" />
                    {t('rubric.promptLocked')}
                  </Badge>
                )}
                <span className="font-mono text-2xs text-muted">{section.key}</span>
              </div>
              {/* `scroll-x` — uzun qatorlar sahifani gorizontal
                  cho'zmasligi kerak */}
              <pre className="scroll-x max-h-64 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-muted">
                {section.text.trim()}
              </pre>
            </div>
          ))}
        <p className="text-2xs leading-relaxed text-muted/80">
          {t('rubric.promptNote')}
        </p>
      </CardBody>
    </Card>
  )
}
