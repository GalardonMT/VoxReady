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
import { CancelExerciseModal } from '../../../components/spokesperson/CancelExerciseModal';
import { useAuth } from '../../../context/AuthContext';
import { ProtectedRoute } from '../../../components/auth/ProtectedRoute';
import type { SessionSetup } from '../../../services/sessionFlowService';

export default function SpokespersonPage() {
  return (
    <ProtectedRoute allowedRoles={['spokesperson']}>
      <SpokespersonContent />
    </ProtectedRoute>
  );
}

function SpokespersonContent() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const [voceroScreen, setVoceroScreen] = useState<VoceroScreen>('u1');
  const [selectedLesson, setSelectedLesson] = useState<string>('Mensajes puente (Bridging)');
  const [activeSessionId, setActiveSessionId] = useState<string>('session-crisis-001');
  const [activeScenarioId, setActiveScenarioId] = useState<string>('crisis-voceria-01');

  // Estado para interceptar salidas accidentales durante la ejercitación
  const [pendingNav, setPendingNav] = useState<{
    type: 'screen' | 'logout';
    screen?: VoceroScreen;
    extra?: string;
  } | null>(null);

  const [selectedSession, setSelectedSession] = useState<{
    setup: SessionSetup;
    userId: string;
    clientId: string | null;
  } | null>(null);

  const activeSession =
    selectedSession &&
    selectedSession.userId === user?.userId &&
    selectedSession.clientId === user?.clientId
      ? selectedSession.setup
      : null;

  if (!user) return null; // guaranteed by ProtectedRoute

  const handleVoceroNavigate = (screen: VoceroScreen, extra?: string) => {
    if (extra && screen === 'lesson') {
      setSelectedLesson(extra);
    }
    if (screen === 'u3') {
      if (extra) setActiveScenarioId(extra);
      const newSession = `session-${extra || 'crisis'}-${Date.now()}`;
      setActiveSessionId(newSession);
    }
    setVoceroScreen(screen);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Interceptar navegación desde cabecera si hay ejercitación activa (u4)
  const handleHeaderNavigate = (screen: VoceroScreen, extra?: string) => {
    if (voceroScreen === 'u4') {
      setPendingNav({ type: 'screen', screen, extra });
      return;
    }
    handleVoceroNavigate(screen, extra);
  };

  const handleHeaderLogout = () => {
    if (voceroScreen === 'u4') {
      setPendingNav({ type: 'logout' });
      return;
    }
    logout();
    router.push('/login');
  };

  // Confirmar cancelación por navegación: descartar sesión sin mandar nada a la BD y continuar
  const handleConfirmPendingNav = () => {
    const nav = pendingNav;
    setPendingNav(null);
    setSelectedSession(null); // Descartar sesión activa (no se guarda nada)

    if (nav?.type === 'logout') {
      logout();
      router.push('/login');
    } else if (nav?.type === 'screen' && nav.screen) {
      handleVoceroNavigate(nav.screen, nav.extra);
    }
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
        <div className="vocero-brand" onClick={() => handleHeaderNavigate('u1')} style={{ cursor: 'pointer' }}>
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
              onClick={() => handleHeaderNavigate(item.id)}
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
            onClick={handleHeaderLogout}
            title="Cerrar sesión"
          >
            <span>⎋</span>
            <span>Salir</span>
          </button>
        </div>
      </header>

      <main className="canvas">
        {voceroScreen === 'u1' && <HomePracticeView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u2' && (
          <ScenarioCatalog
            key={`${user.userId}:${user.clientId}`}
            onNavigate={handleVoceroNavigate}
            onSelected={(setup) => {
              setSelectedSession({ setup, userId: user.userId, clientId: user.clientId });
              setActiveSessionId(setup.sessionId);
              setActiveScenarioId(setup.scenarioId);
              setVoceroScreen('u3');
            }}
          />
        )}
        {voceroScreen === 'u3' && (
          <TechConsentView
            setup={activeSession ?? undefined}
            onNavigate={handleVoceroNavigate}
            onCancel={() => {
              setSelectedSession(null);
              handleVoceroNavigate('u2');
            }}
            onBegin={() => {
              if (activeSession) {
                setSelectedSession({
                  setup: { ...activeSession, status: 'consented' },
                  userId: user.userId,
                  clientId: user.clientId
                });
              }
              setVoceroScreen('u4');
            }}
          />
        )}
        {voceroScreen === 'u4' && (
          <LiveSessionView
            onNavigate={handleVoceroNavigate}
            sessionId={activeSessionId}
            scenarioId={activeScenarioId}
            setup={activeSession ?? undefined}
            onSessionComplete={(sId) => setActiveSessionId(sId)}
            onCancel={() => {
              setSelectedSession(null);
              handleVoceroNavigate('u2');
            }}
          />
        )}
        {voceroScreen === 'u5' && (
          <AnalyzingView
            onNavigate={handleVoceroNavigate}
            sessionId={activeSessionId}
          />
        )}
        {voceroScreen === 'u6' && (
          <CoachReportView
            onNavigate={handleVoceroNavigate}
            sessionId={activeSessionId}
          />
        )}
        {voceroScreen === 'u7' && <ProgressView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'lesson' && (
          <LessonView lessonTitle={selectedLesson} onNavigate={handleVoceroNavigate} />
        )}
      </main>

      {/* Modal de confirmación al intentar salir o cambiar de pestaña durante la ejercitación */}
      <CancelExerciseModal
        isOpen={pendingNav !== null}
        reason="nav_leave"
        onContinue={() => setPendingNav(null)}
        onConfirmCancel={handleConfirmPendingNav}
      />
    </div>
  );
}
