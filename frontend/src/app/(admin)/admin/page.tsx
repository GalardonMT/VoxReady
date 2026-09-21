'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ClientDashboard, AdminScreen } from '../../../components/client-admin/ClientDashboard';
import { TopicEditorView } from '../../../components/client-admin/TopicEditorView';
import { RetentionPolicyView } from '../../../components/client-admin/RetentionPolicyView';
import { useAuth } from '../../../context/AuthContext';

export default function AdminPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [adminScreen, setAdminScreen] = useState<AdminScreen>('a1');
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      router.push('/login');
    }
  }, [user, router]);

  if (!user) {
    return null;
  }

  const handleAdminNavigate = (screen: AdminScreen, topicId?: string | null) => {
    setSelectedTopicId(topicId ?? null);
    setAdminScreen(screen);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };


  const adminNavItems: { id: AdminScreen; label: string; icon: string }[] = [
    { id: 'a1', label: 'Panel del Cliente', icon: '📊' },
    { id: 'a2', label: 'Editor de Tema', icon: '✏️' },
    { id: 'a3', label: 'Política de Retención', icon: '🛡️' }
  ];

  return (
    <div className="platform-container">
      <header className="vocero-header">
        <div className="vocero-brand" onClick={() => handleAdminNavigate('a1')} style={{ cursor: 'pointer' }}>
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
          🏢 {user.clientName || 'Visum Corp'}
        </div>

        <nav className="vocero-nav-tabs">
          {adminNavItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`vtab ${adminScreen === item.id ? 'active' : ''}`}
              onClick={() => handleAdminNavigate(item.id)}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="vocero-user">
          <div className="uava" style={{ backgroundColor: 'var(--accent2)' }}>
            {user.initials}
          </div>
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

      <main className="canvas">
        {adminScreen === 'a1' && <ClientDashboard onNavigate={handleAdminNavigate} />}
        {adminScreen === 'a2' && (
          <TopicEditorView topicId={selectedTopicId} onNavigate={handleAdminNavigate} />
        )}
        {adminScreen === 'a3' && <RetentionPolicyView />}
      </main>

    </div>
  );
}
