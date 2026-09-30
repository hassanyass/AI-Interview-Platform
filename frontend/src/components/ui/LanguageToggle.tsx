import { useState, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';

export function LanguageToggle() {
  const { i18n } = useTranslation();
  const [lang, setLang] = useState(localStorage.getItem('preferred-lang') || 'en');

  // R7: this used to set `<html lang>`/`<html dir>` and persist the choice
  // itself, which meant direction only existed on pages that happened to
  // render this button. `i18n.ts` owns all three now, keyed off
  // `languageChanged`; the toggle just asks for the language.
  useEffect(() => {
    if (i18n.language !== lang) {
      i18n.changeLanguage(lang);
    }
  }, [lang, i18n]);

  const toggleLanguage = () => {
    setLang(lang === 'en' ? 'ar' : 'en');
  };

  return (
    <Button 
      variant="ghost" 
      onClick={toggleLanguage} 
      className="flex h-11 items-center gap-2 text-sm font-medium text-foreground hover:bg-muted lg:h-10"
    >
      <Globe className="h-4 w-4" />
      {lang === 'en' ? 'العربية' : 'English'}
    </Button>
  );
}
