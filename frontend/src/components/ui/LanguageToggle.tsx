import { useState, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';

export function LanguageToggle() {
  const { i18n } = useTranslation();
  const [lang, setLang] = useState(localStorage.getItem('preferred-lang') || 'en');

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    localStorage.setItem('preferred-lang', lang);
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
      className="flex items-center gap-2 text-sm font-medium text-foreground hover:bg-muted"
    >
      <Globe className="h-4 w-4" />
      {lang === 'en' ? 'العربية' : 'English'}
    </Button>
  );
}
