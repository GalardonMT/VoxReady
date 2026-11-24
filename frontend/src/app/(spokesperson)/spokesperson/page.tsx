'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { HomePracticeView, VoceroScreen } from '../../../components/spokesperson/HomePracticeView';
import { ScenarioCatalog } from '../../../components/spokesperson/ScenarioCatalog';
import { TechConsentView } from '../../../components/spokesperson/TechConsentView';
import { LiveSessionView } from '../../../components/spokesperson/LiveSessionView';
import { AnalyzingView } from '../../../components/spokesperson/AnalyzingView';
import { CoachReportView } from '../../../components/spokesperson/CoachReportView';
import { FullVisumReportView } from '../../../components/spokesperson/FullVisumReportView';
import { ProgressView } from '../../../components/spokesperson/ProgressView';
import { LessonView } from '../../../components/spokesperson/LessonView';
import { CancelExerciseModal } from '../../../components/spokesperson/CancelExerciseModal';
import { useAuth } from '../../../context/AuthContext';
import { ProtectedRoute } from '../../../components/auth/ProtectedRoute';
import type { SessionSetup } from '../../../services/sessionFlowService';
import { BookOpen, ChartNoAxesCombined, ClipboardList, House } from 'lucide-react';
import { PlatformHeader } from '../../../components/common/PlatformHeader';
import { SectionNavigation, type SectionNavigationItem } from '../../../components/common/SectionNavigation';

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
  const [selectedLesson, setSelectedLesson] = useState<string>('');
  const [lessonReturnScreen, setLessonReturnScreen] = useState<VoceroScreen>('u1');
  const [practiceScenarioId, setPracticeScenarioId] = useState<string | null>(null);
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
    if (screen === 'lesson') {
      if (voceroScreen !== 'lesson') setLessonReturnScreen(voceroScreen);
      setSelectedLesson(extra ?? '');
    }
    if (screen === 'u2') setPracticeScenarioId(extra || null);
    if (extra && (screen === 'u8' || screen === 'u6')) {
      setActiveSessionId(extra);
    }
    if (screen === 'u3') {
      if (extra) setActiveScenarioId(extra);
      if (!selectedSession) {
        const newSession = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`;
        setActiveSessionId(newSession);
      }
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

  const voceroNavItems: SectionNavigationItem<VoceroScreen>[] = [
    { id: 'u1', label: 'Inicio', icon: House },
    { id: 'u2', label: 'Catálogo', icon: ClipboardList },
    { id: 'u7', label: 'Mi Progreso', icon: ChartNoAxesCombined },
    { id: 'lesson', label: 'Microlecciones', icon: BookOpen }
  ];

  return (
    <div className="platform-container">
      <PlatformHeader
        navigationLabel="Navegación del vocero"
        navigation={<SectionNavigation items={voceroNavItems} activeScreen={voceroScreen} onNavigate={handleHeaderNavigate} />}
        user={user}
        roleLabel="Vocero"
        onHome={() => handleHeaderNavigate('u1')}
        onLogout={handleHeaderLogout}
      />

      <main className="canvas">
        {voceroScreen === 'u1' && <HomePracticeView onNavigate={handleVoceroNavigate} />}
        {voceroScreen === 'u2' && (
          <ScenarioCatalog
            key={`${user.userId}:${user.clientId}`}
            focusScenarioId={practiceScenarioId}
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
            key={activeSessionId}
            onNavigate={handleVoceroNavigate}
            sessionId={activeSessionId}
          />
        )}
        {voceroScreen === 'u8' && (
          <FullVisumReportView
            key={activeSessionId}
            onNavigate={handleVoceroNavigate}
            sessionId={activeSessionId}
          />
        )}
        {voceroScreen === 'u7' && (
          <ProgressView
            onNavigate={handleVoceroNavigate}
            onSessionStart={(setup) => {
              setSelectedSession({ setup, userId: user.userId, clientId: user.clientId });
              setActiveSessionId(setup.sessionId);
              setActiveScenarioId(setup.scenarioId);
              setVoceroScreen('u3');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />
        )}
        {voceroScreen === 'lesson' && (
          <LessonView key={selectedLesson || 'catalog'} lessonReference={selectedLesson || undefined} onBack={() => handleVoceroNavigate(lessonReturnScreen)}
            onPracticeScenario={(scenarioId) => handleVoceroNavigate('u2', scenarioId)} />
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
