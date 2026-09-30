'use client';

import React, { useState } from 'react';
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
import { RoleGate } from '../../../components/auth/RoleGate';
import type { SessionSetup } from '../../../services/sessionFlowService';

export default function SpokespersonPage() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const [voceroScreen, setVoceroScreen] = useState<VoceroScreen>('u1');
  const [selectedLesson, setSelectedLesson] = useState<string>('Mensajes puente (Bridging)');
  const [selectedSession, setSelectedSession] = useState<{ setup: SessionSetup; userId: string; clientId: string | null } | null>(null);
  const activeSession = selectedSession && selectedSession.userId === user?.userId && selectedSession.clientId === user?.clientId ? selectedSession.setup : null;

  const displayScreen = !activeSession && (voceroScreen === 'u3' || voceroScreen === 'u4') ? 'u2' : voceroScreen;

  if (!user) return <RoleGate role="spokesperson">{null}</RoleGate>;

  const handleVoceroNavigate = (screen: VoceroScreen, extra?: string) => {
    if ((screen === 'u3' || screen === 'u4') && !activeSession) screen = 'u2';
    if (screen === 'u4' && activeSession?.status !== 'consented') screen = 'u3';
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
    <RoleGate role="spokesperson"><div className="platform-container">
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
              className={`vtab ${displayScreen === item.id ? 'active' : ''}`}
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
        {displayScreen === 'u1' && <HomePracticeView onNavigate={handleVoceroNavigate} />}
        {displayScreen === 'u2' && <ScenarioCatalog key={`${user.userId}:${user.clientId}`} onSelected={(setup) => {
          setSelectedSession({ setup, userId: user.userId, clientId: user.clientId });
          setVoceroScreen('u3');
        }} />}
        {displayScreen === 'u3' && activeSession && <TechConsentView key={activeSession.sessionId} setup={activeSession}
          onCancel={() => { setSelectedSession(null); handleVoceroNavigate('u2'); }}
          onBegin={() => {
            setSelectedSession({ setup: { ...activeSession, status: 'consented' }, userId: user.userId, clientId: user.clientId });
            setVoceroScreen('u4');
          }} />}
        {displayScreen === 'u4' && activeSession?.status === 'consented' && <LiveSessionView setup={activeSession} onNavigate={handleVoceroNavigate} />}
        {displayScreen === 'u5' && <AnalyzingView onNavigate={handleVoceroNavigate} />}
        {displayScreen === 'u6' && <CoachReportView onNavigate={handleVoceroNavigate} />}
        {displayScreen === 'u7' && <ProgressView onNavigate={handleVoceroNavigate} />}
        {displayScreen === 'lesson' && (
          <LessonView lessonTitle={selectedLesson} onNavigate={handleVoceroNavigate} />
        )}
      </main>
    </div></RoleGate>
  );
}
