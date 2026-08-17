/**
 * AI sozlamalari — YAGONA joy.
 *
 * Ikkita MUSTAQIL blok, chunki ular alohida ish:
 *
 *   🎙  Audio → matn   — yozuvni tinglab matnga o'giradi
 *   ✨  Tahlil          — o'sha matnni rubrika bo'yicha baholaydi
 *
 * Ular bir-biriga bog'liq EMAS: audioni Gemini qilib, tahlilni Claude
 * qilishi mumkin. Shuning uchun har blokda o'z provayderi, o'z modeli
 * va o'z «Tekshirish» tugmasi bor.
 *
 * ⚠️ NIMA OLIB TASHLANDI VA NEGA. Ilgari bu sahifada bir nechta
 * takrorlanuvchi maydon turardi: eski `asr.*` va `llm.*` bloklari
 * (ular hech qayerda o'qilmasdi), har bir provayderning kaliti — hatto
 * ishlatilmayotganiniki ham, va model uchun erkin matn maydoni.
 * Admin ikkita bir xil ko'rinadigan ro'yxatni ko'rar, qaysi biri
 * haqiqiy ishlashini bilmasdi.
 *
 * Endi ekranda faqat ishlaydigan narsa turadi: provayder, model
 * (vendordan JONLI olingan ro'yxatdan) va TANLANGAN provayderning
 * kaliti. Boshqa provayderlarning kalit maydonlari ko'rinmaydi.
 */

import { Check, KeyRound, Mic, Sparkles, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  useAiModels,
  useAiProviders,
  useAiTest,
  type AiModelCatalog,
  type AiProvider,
  type AiRole,
  type AiTestResult,
} from '@/modules/settings/api'
import { fieldOf, type SettingGroup } from '@/modules/settings/types'
import { cn } from '@/shared/lib/utils'
import { Badge, Button, Input, Label, Select, Skeleton } from '@/shared/ui/primitives'

const ROLES: { role: AiRole; icon: typeof Mic }[] = [
  { role: 'asr', icon: Mic },
  { role: 'llm', icon: Sparkles },
]

/** AI blokidan tashqarida chizilmasligi kerak bo'lgan maydonlar.
 *
 *  Ular shu komponent ichida ko'rsatiladi, shuning uchun umumiy
 *  maydonlar ro'yxati ularni takrorlamasligi kerak. */
export function isAiManagedField(key: string): boolean {
  return (
    key === 'ai.asr_provider' ||
    key === 'ai.llm_provider' ||
    key === 'ai.asr_model' ||
    key === 'ai.llm_model' ||
    key.endsWith('_api_key')
  )
}

export function AiSection({
  group,
  draft,
  dirty,
  canEdit,
  onChange,
}: {
  group: SettingGroup
  draft: Record<string, unknown>
  /** Saqlanmagan o'zgarishlar bormi — sinov saqlangan qiymatlarni oladi */
  dirty: boolean
  canEdit: boolean
  onChange: (key: string, value: unknown) => void
}) {
  const providers = useAiProviders()
  const catalogs = useAiModels()

  if (providers.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {ROLES.map(({ role, icon }) => (
        <RoleBlock
          key={role}
          role={role}
          icon={icon}
          group={group}
          providers={providers.data ?? []}
          catalog={catalogs.data?.find((item) => item.role === role)}
          catalogLoading={catalogs.isLoading}
          draft={draft}
          dirty={dirty}
          canEdit={canEdit}
          onChange={onChange}
        />
      ))}
    </div>
  )
}

/* ── Bitta rol: provayder + model + kalit ─────────────────────── */

function RoleBlock({
  role,
  icon: Icon,
  group,
  providers,
  catalog,
  catalogLoading,
  draft,
  dirty,
  canEdit,
  onChange,
}: {
  role: AiRole
  icon: typeof Mic
  group: SettingGroup
  providers: AiProvider[]
  catalog: AiModelCatalog | undefined
  catalogLoading: boolean
  draft: Record<string, unknown>
  dirty: boolean
  canEdit: boolean
  onChange: (key: string, value: unknown) => void
}) {
  const { t } = useTranslation()
  const test = useAiTest()

  const providerKey = `ai.${role}_provider`
  const modelKey = `ai.${role}_model`

  const usable = providers.filter((item) => item.roles.includes(role))
  const savedProvider = String(fieldOf(group, providerKey)?.value ?? '')
  const provider =
    draft[providerKey] === undefined ? savedProvider : String(draft[providerKey])
  const current = usable.find((item) => item.key === provider) ?? null

  const savedModel = String(fieldOf(group, modelKey)?.value ?? '')
  const model = draft[modelKey] === undefined ? savedModel : String(draft[modelKey])

  /* Model ro'yxati faqat SAQLANGAN provayder uchun to'g'ri: katalog
     backenddan keladi va u bazadagi tanlovga qaraydi. Admin provayderni
     endigina almashtirgan bo'lsa — zaxira ro'yxatni ko'rsatamiz,
     saqlagach jonlisi keladi. */
  const fresh = catalog && catalog.provider === provider
  const options = fresh ? catalog.models : (current?.models[role] ?? [])
  const fallbackModel = current?.default_models[role] ?? ''

  const keySetting = current?.api_key_setting ?? ''
  const keyField = keySetting ? fieldOf(group, keySetting) : undefined
  const keySet = Boolean(keyField?.is_set)
  const keyDraft = keySetting ? String(draft[keySetting] ?? '') : ''

  return (
    <div className="rounded-2xl border border-border/70 p-4">
      {/* Sarlavha + holat */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="icon-tile size-9 bg-surface-2 text-muted">
            <Icon className="size-4" />
          </span>
          <div>
            <div className="text-sm font-semibold">{t(`settings.ai.role.${role}`)}</div>
            <p className="text-2xs text-muted">{t(`settings.ai.roleHint.${role}`)}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge tone={keySet || keyDraft ? 'good' : 'neutral'}>
            {keySet || keyDraft ? (
              <Check className="size-3" />
            ) : (
              <KeyRound className="size-3" />
            )}
            {keySet || keyDraft ? t('settings.ai.keySet') : t('settings.ai.keyMissing')}
          </Badge>
          {canEdit && (
            <Button
              size="sm"
              variant="secondary"
              disabled={dirty || test.isPending}
              onClick={() => test.mutate(role)}
              title={dirty ? t('settings.ai.saveFirst') : undefined}
            >
              <Zap className="size-3.5" />
              {test.isPending ? t('settings.ai.testing') : t('settings.ai.test')}
            </Button>
          )}
        </div>
      </div>

      {/* Provayder · Model */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <Label className="mb-1.5">{t('settings.ai.provider')}</Label>
          <Select
            className="h-10 w-full"
            disabled={!canEdit}
            value={provider}
            onChange={(e) => {
              onChange(providerKey, e.target.value)
              // Model eski provayderniki bo'lib qolmasin — tozalaymiz,
              // shunda backend yangi provayderning standartini oladi
              onChange(modelKey, '')
            }}
          >
            {usable.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </Select>
        </div>

        <div>
          <Label className="mb-1.5">
            {t('settings.ai.model')}
            {fresh && catalog?.source === 'live' && (
              <span className="ml-1.5 text-2xs font-normal text-good">
                {t('settings.ai.live')}
              </span>
            )}
          </Label>
          {catalogLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <Select
              className="h-10 w-full"
              disabled={!canEdit}
              value={model}
              onChange={(e) => onChange(modelKey, e.target.value)}
            >
              {/* Bo'sh qiymat = provayderning standarti. Uni ro'yxatdan
                  olib tashlamaymiz: admin «o'zi bilsin» deyishi mumkin */}
              <option value="">
                {t('settings.ai.autoModel', { model: fallbackModel })}
              </option>
              {options.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
              {/* Saqlangan model ro'yxatdan chiqib ketgan bo'lsa ham
                  ko'rinib tursin — aks holda tanlov jimgina o'zgarardi */}
              {model && !options.includes(model) && (
                <option value={model}>{model} — {t('settings.ai.unknownModel')}</option>
              )}
            </Select>
          )}
        </div>
      </div>

      {/* Kalit — FAQAT tanlangan provayderniki */}
      {current && (
        <div className="mt-3">
          <Label className="mb-1.5">{current.key_label ?? t('settings.ai.apiKey')}</Label>
          <Input
            type="password"
            disabled={!canEdit}
            placeholder={keySet ? '••••••••' : t('settings.ai.keyPlaceholder')}
            value={keyDraft}
            onChange={(e) => onChange(keySetting, e.target.value)}
          />
          <p className="mt-1 text-2xs text-muted">
            <a
              href={current.docs_url}
              target="_blank"
              rel="noreferrer"
              className="transition-colors duration-250 ease-ios hover:text-accent"
            >
              {current.docs_url}
            </a>
          </p>
        </div>
      )}

      {test.isPending && <Skeleton className="mt-3 h-12 w-full" />}
      {!test.isPending && test.data && <TestResultView result={test.data} />}
      {!test.isPending && test.isError && (
        <p className="mt-3 rounded-xl bg-bad/[0.08] px-3.5 py-3 text-2xs leading-relaxed text-bad">
          {test.error instanceof Error ? test.error.message : t('common.error')}
        </p>
      )}
    </div>
  )
}

/* ── Sinov natijasi ───────────────────────────────────────────
   Xato matni backenddan KELGANICHA ko'rsatiladi: u o'zbekcha va aniq
   («… uchun API kalit kiritilmagan»), biz uni «Xatolik» ga
   almashtirsak foydalanuvchi nima qilishni bilmay qoladi. */

function TestResultView({ result }: { result: AiTestResult }) {
  const { t } = useTranslation()

  return (
    <div
      className={cn(
        'mt-3 flex animate-scale-in items-start gap-2.5 rounded-xl px-3.5 py-3',
        result.ok ? 'bg-good/10' : 'bg-surface-2',
      )}
    >
      <span
        className={cn(
          'mt-0.5 grid size-5 shrink-0 place-items-center rounded-full',
          result.ok ? 'bg-good/20 text-good' : 'bg-muted/20 text-muted',
        )}
      >
        {result.ok ? <Check className="size-3" /> : <KeyRound className="size-3" />}
      </span>

      <div className="min-w-0 text-2xs leading-relaxed">
        {result.ok ? (
          <>
            <p className="font-medium text-good">{t('settings.ai.ok')}</p>
            <p className="mt-0.5 text-muted">
              {result.provider_label} · <span className="font-mono">{result.model}</span> ·{' '}
              <span className="tnum">{result.latency_ms}</span> ms
            </p>
          </>
        ) : (
          <>
            <p className="font-medium">{t('settings.ai.notOk')}</p>
            <p className="mt-0.5 text-muted">{result.error}</p>
          </>
        )}
      </div>
    </div>
  )
}
