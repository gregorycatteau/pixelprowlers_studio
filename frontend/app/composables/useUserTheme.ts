// app/composables/useUserTheme.ts
const STORAGE_KEY = 'pixelprowlers:theme'

type ThemeMode = 'light' | 'dark'
type ThemePreference = ThemeMode | 'system'

/**
 * Gestion du thème utilisateur (light/dark) avec fallback système.
 * Applique les classes .dark et l'attribut data-theme pour alimenter les variantes Tailwind.
 */
export function useUserTheme() {
  const isDark = useState<boolean>('ui:isDark', () => true)
  const preference = useState<ThemePreference>('ui:theme-preference', () => 'system')

  const applyTheme = (dark: boolean) => {
    isDark.value = dark

    if (import.meta.client) {
      const root = document.documentElement
      root.classList.toggle('dark', dark)
      root.setAttribute('data-theme', dark ? 'dark' : 'light')
    }
  }

  const resolveSystemDark = () =>
    import.meta.client
      ? window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
      : true

  const syncTheme = (pref: ThemePreference, persist = false) => {
    const dark = pref === 'dark' || (pref === 'system' && resolveSystemDark())
    applyTheme(dark)

    if (!import.meta.client) return

    if (persist && pref !== 'system') {
      window.localStorage.setItem(STORAGE_KEY, pref)
    } else if (pref === 'system') {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }

  const setThemePreference = (pref: ThemePreference, persist = true) => {
    preference.value = pref
    syncTheme(pref, persist)
  }

  onBeforeMount(() => {
    if (!import.meta.client) return

    const stored = window.localStorage.getItem(STORAGE_KEY) as ThemePreference | null

    if (stored === 'light' || stored === 'dark') {
      preference.value = stored
      syncTheme(stored, false)
    } else {
      preference.value = 'system'
      syncTheme('system', false)
    }
  })

  onMounted(() => {
    if (!import.meta.client) return

    const media = window.matchMedia('(prefers-color-scheme: dark)')

    const handleSchemeChange = (event: MediaQueryListEvent) => {
      if (preference.value === 'system') {
        applyTheme(event.matches)
      }
    }

    media.addEventListener('change', handleSchemeChange, { passive: true })

    onBeforeUnmount(() => {
      media.removeEventListener('change', handleSchemeChange)
    })
  })

  const toggleTheme = () => {
    const nextMode: ThemeMode = isDark.value ? 'light' : 'dark'
    setThemePreference(nextMode)
  }

  return {
    isDark,
    preference,
    toggleTheme,
    setThemePreference,
  }
}
