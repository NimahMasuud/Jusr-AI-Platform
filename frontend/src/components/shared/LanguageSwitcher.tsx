import { Globe } from "lucide-react";

import { useLanguage } from "../../i18n/LanguageContext";

function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage();

  return (
    <div
      className="language-switch"
      role="group"
      aria-label="Select language"
      data-no-translate
    >
      <Globe size={16} aria-hidden="true" />
      <button
        type="button"
        className={language === "en" ? "active" : ""}
        onClick={() => setLanguage("en")}
        aria-pressed={language === "en"}
        title="English"
      >
        English
      </button>
      <button
        type="button"
        className={language === "ar" ? "active" : ""}
        onClick={() => setLanguage("ar")}
        aria-pressed={language === "ar"}
        title="العربية"
      >
        العربية
      </button>
    </div>
  );
}

export default LanguageSwitcher;
