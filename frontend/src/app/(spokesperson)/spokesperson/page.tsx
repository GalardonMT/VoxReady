'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { HomePracticeView, VoceroScreen } from '../../../components/spokesperson/HomePracticeView';
import { ScenarioCatalog } from '../../../components/spokesperson/ScenarioCatalog';
import { TechConsentView } from '../../../components/spokesperson/TechConsentView';
import { LiveSessionView } from '../../../components/spokesperson/LiveSessionView';
import { AnalyzingView } from '../../../components/spokesperson/AnalyzingView';
import { CoachReportView } from '../../../components/spokesperson/CoachReportView';
import { ProgressView } from '../../../components/spokesperson/ProgressView';
import { LessonView } from '../../../components/spokesperson/LessonView';
import { useAuth } from '../../../context/AuthContext';

export default function SpokespersonPage() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const [voceroScreen, setVoceroScreen] = useState<VoceroScreen>('u1');
  const [selectedLesson, setSelectedLesson] = useState<string>('Mensajes puente (Bridging)');

  useEffect(() => {
    if (!user) {
      router.push('/login');
    }
  }, [user, router]);

  if (!user) {
    return null;
  }

  const handleVoceroNavigate = (screen: VoceroScreen, extra?: string) => {
    if (extra && screen === 'lesson') {
      setSelectedLesson(extra);
    }
    setVoceroScreen(screen);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const voceroNavItems: { id: VoceroScreen; label: string; icon: string }[] = [
    { id: 'u1', label: 'Inicio', icon: '🏠' },
    { id: 'u2', label: 'Catálogo', icon: '📋' },
    { id: 'u7', label: 'Mi Progreso', icon: '📈' },
    { id: 'lesson', label: 'Microlección', icon: '📖' }
  ];

  return (
    <div className="platform-container">
      <header className="vocero-header">
        <div className="vocero-brand" onClick={() => handleVoceroNavigate('u1')} style={{ cursor: 'pointer' }}>
          <img
            src="/VoxReady_logo.png"
            alt="VoxReady"
            style={{ height: '32px', width: 'auto', display: 'block' }}
          />
        </div>

        <nav className="vocero-nav-tabs">
          {voceroNavItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`vtab ${voceroScreen === item.id ? 'active' : ''}`}
              onClick={() => handleVoceroNavigate(item.id)}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="vocero-user">
          <div className="uava">{user.initials}</div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span className="uname">{user.displayName}</span>
            <span style={{ fontSize: '10.5px', color: 'var(--muted)' }}>Vocero</span>
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
        {voceroScreen === 'u1' && <HomePracticeView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u2' && <ScenarioCatalog onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u3' && <TechConsentView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u4' && <LiveSessionView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u5' && <AnalyzingView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u6' && <CoachReportView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u7' && <ProgressView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'lesson' && (
          <LessonView lessonTitle={selectedLesson} onNavigate={handleVoceroNavigate} />
        )}
      </main>
    </div>
  );
}
