'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { MasterDashboard, MasterScreen } from '../../../components/master/MasterDashboard';
import { RubricEditorView } from '../../../components/master/RubricEditorView';
import { LabelingQueueView } from '../../../components/master/LabelingQueueView';
import { useAuth } from '../../../context/AuthContext';

export default function MasterPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [masterScreen, setMasterScreen] = useState<MasterScreen>('m1');

  useEffect(() => {
    if (!user) {
      router.push('/login');
    }
  }, [user, router]);

  if (!user) {
    return null;
  }

  const handleMasterNavigate = (screen: MasterScreen) => {
    setMasterScreen(screen);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const masterNavItems: { id: MasterScreen; label: string; icon: string }[] = [
    { id: 'm1', label: 'Panel Maestro', icon: '📊' },
    { id: 'm2', label: 'Editor de Rúbrica', icon: '📐' },
    { id: 'm3', label: 'Cola de Etiquetado', icon: '🎯' }
  ];

  return (
    <div className="platform-container">
      <header className="vocero-header">
        <div className="vocero-brand" onClick={() => handleMasterNavigate('m1')} style={{ cursor: 'pointer' }}>
          <img
            src="/VoxReady_logo.png"
            alt="VoxReady"
            style={{ height: '32px', width: 'auto', display: 'block' }}
          />
        </div>

        <div
          className="tagm"
          style={{
            background: 'var(--soft)',
            color: 'var(--ink)',
            fontWeight: 600,
            fontSize: '11.5px',
            padding: '3px 10px'
          }}
        >
          👑 VoxReady Central · Estándar Global
        </div>

        <nav className="vocero-nav-tabs">
          {masterNavItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`vtab ${masterScreen === item.id ? 'active' : ''}`}
              onClick={() => handleMasterNavigate(item.id)}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="vocero-user">
          <div
            className="uava"
            style={{
              backgroundColor: 'var(--accent)',
              color: '#ffffff'
            }}
          >
            {user.initials}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span className="uname">{user.displayName}</span>
            <span style={{ fontSize: '10.5px', color: 'var(--muted)' }}>Configurador maestro</span>
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

      <main className="canvas">
        {masterScreen === 'm1' && <MasterDashboard onNavigate={handleMasterNavigate} />}
        {masterScreen === 'm2' && <RubricEditorView onNavigate={handleMasterNavigate} />}
        {masterScreen === 'm3' && <LabelingQueueView onNavigate={handleMasterNavigate} />}
      </main>
    </div>
  );
}
