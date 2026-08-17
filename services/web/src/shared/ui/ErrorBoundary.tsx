/**
 * Render vaqtidagi xatolikni ushlaydi.
 *
 * NEGA KERAK. React'da render ichida otilgan xato ushlanmasa, u BUTUN
 * daraxtni yechib tashlaydi va foydalanuvchi OQ EKRAN ko'radi. Konsolni
 * ochib ko'rmagan odam uchun bu «tizim ishlamayapti» degani, xato qayerda
 * ekani esa hech qanday belgisiz qoladi.
 *
 * Bu haqiqatan bo'lgan: qo'ng'iroq tafsiloti sahifasida shartli
 * `useEffect` «Rendered more hooks than during the previous render»
 * xatosini bergan va sahifa umuman ochilmagan. O'shanda nosozlikni
 * topish uchun konsolga qarash kerak bo'ldi — foydalanuvchi buni
 * qilmaydi, u shunchaki «ochilmadi» deb aytadi.
 *
 * Bu himoya xatoni TUZATMAYDI va yashirmaydi ham: konsolga to'liq
 * yozadi, ekranda esa o'qiladigan xabar va chiqish yo'lini beradi.
 * Muhim tomoni — qolgan interfeys (menyu, boshqa bo'limlar) ishlashda
 * qoladi, chunki chegara sahifa atrofida.
 */

import { AlertTriangle, RotateCcw } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Chegara qayerda turgani — konsol yozuvida ko'rinadi */
  scope?: string
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // ⚠️ Jim yutib yuborilmaydi. Stack konsolda to'liq turishi kerak,
    // aks holda xatoni tuzatib bo'lmaydi.
    console.error(`[ErrorBoundary${this.props.scope ? `:${this.props.scope}` : ''}]`, {
      message: error.message,
      stack: error.stack,
      componentStack: info.componentStack,
    })
  }

  private reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    /* Matn i18n'dan OLINMAYDI. Bu chegara i18n provayderining o'zi
       yiqilganda ham ishlashi kerak — o'sha holatda `t()` ni chaqirish
       chegara ichida ikkinchi xatoni tug'dirardi. Shuning uchun uch
       tilda qisqa, qat'iy matn. */
    return (
      <div className="grid min-h-[60vh] place-items-center p-6">
        <div className="w-full max-w-md rounded-2xl bg-surface p-6 text-center shadow-pop">
          <div className="mx-auto mb-3 grid size-11 place-items-center rounded-xl bg-bad/10">
            <AlertTriangle className="size-5 text-bad" />
          </div>
          <h2 className="text-base font-semibold">Sahifada xatolik yuz berdi</h2>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            Bu bo'lim ochilmadi. Qolgan bo'limlar ishlashda davom etadi.
            <br />
            Ошибка на странице · Something went wrong
          </p>

          {/* Texnik tafsilot — yig'ilgan holda. Xodim uni nusxalab
              yuborishi mumkin, lekin ekranni qo'rqitib turmaydi. */}
          <details className="mt-3 text-left">
            <summary className="cursor-pointer text-2xs text-muted hover:text-text">
              Texnik tafsilot
            </summary>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-2.5 text-[10px] leading-relaxed text-muted">
              {error.message}
            </pre>
          </details>

          <div className="mt-4 flex justify-center gap-2">
            <button
              onClick={this.reset}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-accent px-4 text-xs font-medium text-white transition-all duration-250 ease-ios active:scale-[0.97]"
            >
              <RotateCcw className="size-3.5" />
              Qayta urinish
            </button>
            <button
              onClick={() => window.location.reload()}
              className="h-9 rounded-xl bg-surface-2 px-4 text-xs font-medium transition-all duration-250 ease-ios active:scale-[0.97] hover:bg-surface-2/70"
            >
              Sahifani yangilash
            </button>
          </div>
        </div>
      </div>
    )
  }
}
