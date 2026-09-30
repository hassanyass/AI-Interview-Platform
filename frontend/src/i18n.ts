import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { applyDocumentLanguage } from './lib/documentLanguage';

import enTranslation from './locales/en.json';
import arTranslation from './locales/ar.json';

const resources = {
  en: {
    translation: enTranslation
  },
  ar: {
    translation: arTranslation
  }
};

const savedLang = localStorage.getItem('preferred-lang') || 'en';

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: savedLang,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false 
    }
  });

// R7: `<html lang>`/`<html dir>` are set HERE, not by the language toggle.
// Applied once at init -- before React mounts, so there is no flash of the
// wrong direction -- and again whenever the language changes, including
// from anywhere that is not the toggle. Before this, a page without the
// toggle (`/login`, the interview's loading and error branches) rendered
// Arabic text in a left-to-right layout and never corrected itself.
applyDocumentLanguage(i18n.language || savedLang);
i18n.on('languageChanged', (lng) => {
  applyDocumentLanguage(lng);
  localStorage.setItem('preferred-lang', lng);
});

export default i18n;
