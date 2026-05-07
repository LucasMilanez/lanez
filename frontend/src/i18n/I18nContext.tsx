import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { en, pt, type Locale, type Translations } from ".";

const dictionaries: Record<Locale, Translations> = { en, pt };
const STORAGE_KEY = "lanez_locale";

function getInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored && stored in dictionaries) return stored;
  // Detect browser language
  const browserLang = navigator.language.slice(0, 2);
  if (browserLang === "pt") return "pt";
  return "en";
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translations;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem(STORAGE_KEY, newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const t = dictionaries[locale];

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

/**
 * Simple string interpolation: replaces {key} with values.
 * Example: interpolate("Hello {name}", { name: "World" }) => "Hello World"
 */
export function interpolate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? `{${key}}`));
}
