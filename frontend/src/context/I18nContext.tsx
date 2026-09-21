'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { es } from '../locales/es';
import { en } from '../locales/en';
import { pt } from '../locales/pt';

export type Language = 'es' | 'en' | 'pt';

type I18nDictionary = typeof es;

interface I18nContextType {
  lang: Language;
  t: I18nDictionary;
  setLang: (lang: Language) => void;
}

const dictionaries: Record<Language, I18nDictionary> = {
  es,
  en: en as unknown as I18nDictionary,
  pt: pt as unknown as I18nDictionary
};

const I18nContext = createContext<I18nContextType | undefined>(undefined);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>('es');

  useEffect(() => {
    const savedLang = localStorage.getItem('voxready_lang') as Language | null;
    if (savedLang && (savedLang === 'es' || savedLang === 'en' || savedLang === 'pt')) {
      setLangState(savedLang);
    }
  }, []);

  const setLang = (l: Language) => {
    setLangState(l);
    localStorage.setItem('voxready_lang', l);
    document.documentElement.lang = l;
  };

  const t = dictionaries[lang] || es;

  return (
    <I18nContext.Provider value={{ lang, t, setLang }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
}
