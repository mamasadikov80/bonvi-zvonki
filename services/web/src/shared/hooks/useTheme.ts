import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'

const KEY = 'zvonki-theme'

function read(): Theme {
  const value = localStorage.getItem(KEY)
  return value === 'light' || value === 'dark' ? value : 'system'
}

function apply(theme: Theme) {
  if (theme === 'system') {
    delete document.documentElement.dataset.theme
    localStorage.removeItem(KEY)
  } else {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(KEY, theme)
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read)

  useEffect(() => {
    apply(theme)
  }, [theme])

  const setTheme = useCallback((next: Theme) => setThemeState(next), [])

  const toggle = useCallback(() => {
    setThemeState((current) => {
      const isDark =
        current === 'dark' ||
        (current === 'system' &&
          window.matchMedia('(prefers-color-scheme: dark)').matches)
      return isDark ? 'light' : 'dark'
    })
  }, [])

  const isDark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  return { theme, setTheme, toggle, isDark }
}
