'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';

export type ClientAdminScreen = 'a1' | 'a2' | 'a4' | 'a5';

const navItems: { id: ClientAdminScreen; label: string; icon: string }[] = [
  { id: 'a1', label: 'Panel del Cliente', icon: '📊' },
  { id: 'a2', label: 'Voceros', icon: '👥' },
  { id: 'a4', label: 'Escenarios disponibles', icon: '📚' },
  { id: 'a5', label: 'Actividad y uso', icon: '📈' },
];

interface ClientAdminHeaderProps {
  activeScreen: ClientAdminScreen;
  onNavigate: (screen: ClientAdminScreen) => void;
}

export const ClientAdminHeader: React.FC<ClientAdminHeaderProps> = ({ activeScreen, onNavigate }) => {
  const router = useRouter();
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <header className="vocero-header">
      <div className="vocero-brand" onClick={() => onNavigate('a1')} style={{ cursor: 'pointer' }}>
        <img src="/VoxReady_logo.png" alt="VoxReady" style={{ height: '32px', width: 'auto', display: 'block' }} />
      </div>

      <div className="tagm" style={{ background: 'var(--soft)', color: 'var(--ink)', fontWeight: 600, fontSize: '11.5px', padding: '3px 10px' }}>
        🏢 {user.clientName || 'Cliente'}
      </div>

      <nav className="vocero-nav-tabs" aria-label="Navegación del cliente">
        {navItems.map(item => (
          <button
            key={item.id}
            type="button"
            className={`vtab ${activeScreen === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="vocero-user">
        <div className="uava" style={{ backgroundColor: 'var(--accent2)' }}>{user.initials}</div>
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
          <span className="uname">{user.displayName}</span>
          <span style={{ fontSize: '10.5px', color: 'var(--muted)' }}>Admin del cliente</span>
        </div>
        <button
          type="button"
          className="vocero-logout"
          onClick={() => {
            logout();
            router.push('/login');
          }}
          title="Cerrar sesión"
        >
          <span>⎋</span>
          <span>Salir</span>
        </button>
      </div>
    </header>
  );
};
