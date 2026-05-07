import { useI18n } from "./I18nContext";
import { Button } from "@/components/ui/button";

export function LocaleToggle() {
  const { locale, setLocale } = useI18n();

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 text-xs font-semibold"
      onClick={() => setLocale(locale === "en" ? "pt" : "en")}
      aria-label={locale === "en" ? "Switch to Portuguese" : "Mudar para Inglês"}
      title={locale === "en" ? "Switch to Portuguese" : "Mudar para Inglês"}
    >
      {locale === "en" ? "PT" : "EN"}
    </Button>
  );
}
