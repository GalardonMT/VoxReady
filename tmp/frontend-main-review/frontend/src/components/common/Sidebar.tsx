'use client';

import React from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import type { Role } from '../../types/api';

export type ScreenId = 'u1' | 'u2' | 'u3' | 'u4' | 'u5' | 'u6' | 'u7' | 'lesson' | 'a1' | 'a2' | 'a3' | 'm1' | 'm2' | 'm3';

export const Sidebar: React.FC<{ currentScreen: ScreenId; onSelectScreen: (screen: ScreenId) => void }> = ({ currentScreen, onSelectScreen }) => {
  const { t } = useI18n();
  const { user } = useAuth();
  if (!user) return null;
  const ids: Record<Role, ScreenId[]> = {
    spokesperson: ['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7'],
    client_admin: ['a1', 'a2', 'a3'], master_config: ['m1', 'm2', 'm3'],
  };
  return <aside className="sidebar">
    <div className="brand"><img src="/VoxReady_logo.png" alt="VoxReady" style={{ height: 34 }} /><p>{t.brandP}</p></div>
    <div className="role-header">{t.roles[user.role]}</div>
    <nav style={{ flex: 1 }}>{ids[user.role].map((id, index) => <button key={id} type="button" className={`navitem ${currentScreen === id ? 'active' : ''}`} onClick={() => onSelectScreen(id)}><span className="n">{index + 1}</span><span>{t.nav[id as keyof typeof t.nav]}</span></button>)}</nav>
  </aside>;
};
