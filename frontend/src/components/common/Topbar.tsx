'use client';

import React from 'react';
import Image from 'next/image';
import { useI18n, Language } from '../../context/I18nContext';
import { useTheme, Palette } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';

export const Topbar: React.FC = () => {
  const { lang, setLang, t } = useI18n();
  const { theme, toggleTheme, palette, setPalette } = useTheme();
  const { user, logout } = useAuth();

  const palettes: { key: Palette; color: string; label: string }[] = [
    { key: 'voxready', color: '#17354F', label: 'VoxReady' },
    { key: 'teal', color: '#0f6e56', label: 'Teal' },
    { key: 'coral', color: '#b1502b', label: 'Coral' },
    { key: 'violet', color: '#534ab7', label: 'Violet' }
  ];

  return (
    <header className="topbar">
      <span className="tb-title">
        <span style={{ fontSize: '16px' }}>🎙️</span>
        {t.tbTitle}
      </span>

      <div className="tb-right">
        <div className="ctrl">
          <span style={{ fontSize: '14px' }}>🌐</span>
          <select
            className="lang"
            value={lang}
            onChange={(e) => setLang(e.target.value as Language)}
            aria-label="Idioma"
          >
            <option value="es">Español</option>
            <option value="en">English</option>
            <option value="pt">Português</option>
          </select>
        </div>

        <button
          className="iconbtn"
          onClick={toggleTheme}
          title={t.theme}
          aria-label={t.theme}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        <div className="ctrl">
          <span>{t.palette}</span>
          <div className="swatches">
            {palettes.map((p) => (
              <span
                key={p.key}
                className={`sw ${palette === p.key ? 'on' : ''}`}
                style={{ backgroundColor: p.color }}
                onClick={() => setPalette(p.key)}
                title={p.label}
              />
            ))}
          </div>
        </div>

        <div className="logo-slot" title="Cliente: Visum">
          <img
            src="/Visum_logo.png"
            alt="Visum"
            style={{ maxWidth: '98px', maxHeight: '28px', display: 'block' }}
          />
        </div>

        {user && (
          <div className="userchip">
            <div className="uava">{user.initials}</div>
            <div className="umeta">
              <span className="uname">{user.displayName}</span>
              <span className="urole">{t.roles[user.role]}</span>
            </div>
            <button className="logoutbtn" onClick={logout} title={t.login.logout}>
              <span>⎋</span>
              <span>{t.login.logout}</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
