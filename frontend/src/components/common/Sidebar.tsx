'use client';

import React from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { Role } from '../../types/api';

export type ScreenId =
  | 'u1'
  | 'u2'
  | 'u3'
  | 'u4'
  | 'u5'
  | 'u6'
  | 'u7'
  | 'lesson'
  | 'a1'
  | 'a2'
  | 'a3'
  | 'm1'
  | 'm2'
  | 'm3';

interface SidebarProps {
  currentScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentScreen, onSelectScreen }) => {
  const { t } = useI18n();
  const { user, loginAs, testUsers } = useAuth();

  if (!user) return null;

  const roleNavItems: Record<Role, { id: ScreenId; num: number; label: string }[]> = {
    spokesperson: [
      { id: 'u1', num: 1, label: t.nav.u1 },
      { id: 'u2', num: 2, label: t.nav.u2 },
      { id: 'u3', num: 3, label: t.nav.u3 },
      { id: 'u4', num: 4, label: t.nav.u4 },
      { id: 'u5', num: 5, label: t.nav.u5 },
      { id: 'u6', num: 6, label: t.nav.u6 },
      { id: 'u7', num: 7, label: t.nav.u7 }
    ],
    client_admin: [
      { id: 'a1', num: 1, label: t.nav.a1 },
      { id: 'a2', num: 2, label: t.nav.a2 },
      { id: 'a3', num: 3, label: t.nav.a3 }
    ],
    master_config: [
      { id: 'm1', num: 1, label: t.nav.m1 },
      { id: 'm2', num: 2, label: t.nav.m2 },
      { id: 'm3', num: 3, label: t.nav.m3 }
    ]
  };

  const navItems = roleNavItems[user.role] || [];

  const handleSwitchUser = (role: Role) => {
    const targetUser = testUsers.find((u) => u.role === role);
    if (targetUser) {
      loginAs(targetUser);
      if (role === 'spokesperson') onSelectScreen('u1');
      else if (role === 'client_admin') onSelectScreen('a1');
      else if (role === 'master_config') onSelectScreen('m1');
    }
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brandlogo-wrap">
          <img
            src="/VoxReady_logo.png"
            alt="VoxReady"
            style={{ height: '34px', width: 'auto', display: 'block' }}
          />
        </div>
        <p>{t.brandP}</p>
      </div>

      <div className="role-header">{t.roles[user.role]}</div>

      <nav style={{ flex: 1 }}>
        {navItems.map((item) => {
          const isActive = currentScreen === item.id;
          return (
            <div
              key={item.id}
              className={`navitem ${isActive ? 'active' : ''}`}
              onClick={() => onSelectScreen(item.id)}
            >
              <span className="n">{item.num}</span>
              <span>{item.label}</span>
            </div>
          );
        })}
      </nav>

      {/* Role Switcher Demo Helper */}
      <div className="role-switcher-card">
        <div className="title">Cambiar rol (Demo):</div>
        <button
          type="button"
          className={`role-btn ${user.role === 'spokesperson' ? 'active' : ''}`}
          onClick={() => handleSwitchUser('spokesperson')}
        >
          <span>👤</span>
          <span>Vocero (Ana)</span>
        </button>
        <button
          type="button"
          className={`role-btn ${user.role === 'client_admin' ? 'active' : ''}`}
          onClick={() => handleSwitchUser('client_admin')}
        >
          <span>🏢</span>
          <span>Admin (Carlos)</span>
        </button>
        <button
          type="button"
          className={`role-btn ${user.role === 'master_config' ? 'active' : ''}`}
          onClick={() => handleSwitchUser('master_config')}
        >
          <span>⚙️</span>
          <span>Maestro (Marta)</span>
        </button>
      </div>
    </aside>
  );
};
