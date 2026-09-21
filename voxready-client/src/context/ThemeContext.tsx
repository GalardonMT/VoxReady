'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';

export type ThemeMode = 'light' | 'dark';
export type Palette = 'voxready' | 'teal' | 'coral' | 'violet';

interface ThemeContextType {
  theme: ThemeMode;
  palette: Palette;
  toggleTheme: () => void;
  setTheme: (mode: ThemeMode) => void;
  setPalette: (palette: Palette) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>('light');
  const [palette, setPaletteState] = useState<Palette>('voxready');

  useEffect(() => {
    const savedTheme = localStorage.getItem('voxready_theme') as ThemeMode | null;
    const savedPalette = localStorage.getItem('voxready_palette') as Palette | null;
    if (savedTheme) setThemeState(savedTheme);
    if (savedPalette) setPaletteState(savedPalette);
  }, []);

  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('voxready_theme', theme);
  }, [theme]);

  useEffect(() => {
    document.body.setAttribute('data-palette', palette);
    localStorage.setItem('voxready_palette', palette);
  }, [palette]);

  const toggleTheme = () => {
    setThemeState((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  const setTheme = (mode: ThemeMode) => setThemeState(mode);
  const setPalette = (p: Palette) => setPaletteState(p);

  return (
    <ThemeContext.Provider value={{ theme, palette, toggleTheme, setTheme, setPalette }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
