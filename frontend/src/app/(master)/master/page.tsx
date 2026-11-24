'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { MasterDashboard, MasterScreen } from '../../../components/master/MasterDashboard';
import { RubricEditorView } from '../../../components/master/RubricEditorView';
import { LabelingQueueView } from '../../../components/master/LabelingQueueView';
import { TopicCatalogView } from '../../../components/master/TopicCatalogView';
import { MasterTopicEditorView } from '../../../components/master/MasterTopicEditorView';
import { MicrolessonManagerView } from '../../../components/master/MicrolessonManagerView';
import { MetricsEditorView } from '../../../components/master/MetricsEditorView';
import { ClientManagerView } from '../../../components/master/ClientManagerView';
import { useI18n } from '../../../context/I18nContext';
import { useAuth } from '../../../context/AuthContext';
import { ProtectedRoute } from '../../../components/auth/ProtectedRoute';
import { PlatformHeader } from '../../../components/common/PlatformHeader';
import { MasterNavigation } from '../../../components/master/MasterNavigation';

export default function MasterPage() {
  return (
    <ProtectedRoute allowedRoles={['master_config']}>
      <MasterContent />
    </ProtectedRoute>
  );
}

function MasterContent() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [masterScreen, setMasterScreen] = useState<MasterScreen>('m1');
  const [metricsVisited, setMetricsVisited] = useState(false);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const { t } = useI18n();
  const labelingUiEnabled = process.env.NEXT_PUBLIC_LABELING_UI_ENABLED !== 'false';

  if (!user) return null; // guaranteed by ProtectedRoute

  const handleMasterNavigate = (screen: MasterScreen) => {
    if (screen === 'm7') setMetricsVisited(true);
    setMasterScreen(screen);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="platform-container">
      <PlatformHeader
        badge="Configurador maestro"
        navigationLabel="Navegación del configurador maestro"
        navigation={<MasterNavigation activeScreen={masterScreen} labelingEnabled={labelingUiEnabled} onNavigate={handleMasterNavigate} />}
        user={user}
        roleLabel={t.roles[user.role]}
        onHome={() => handleMasterNavigate('m1')}
        onLogout={() => {
          logout();
          router.push('/login');
        }}
      />

      <main className="canvas">
        {masterScreen === 'm1' && <MasterDashboard onNavigate={handleMasterNavigate} labelingEnabled={labelingUiEnabled} />}
        {masterScreen === 'm2' && <RubricEditorView onNavigate={handleMasterNavigate} />}
        {metricsVisited && <div hidden={masterScreen !== 'm7'}><MetricsEditorView onNavigate={handleMasterNavigate} /></div>}
        {labelingUiEnabled && masterScreen === 'm3' && <LabelingQueueView onNavigate={handleMasterNavigate} />}
        {masterScreen === 'm4' && <TopicCatalogView onEdit={id => { setSelectedTopicId(id); handleMasterNavigate('m5'); }} />}
        {masterScreen === 'm5' && <MasterTopicEditorView key={`${user.userId}:${selectedTopicId || 'new'}`} topicId={selectedTopicId}
          onCreated={setSelectedTopicId} onBack={() => handleMasterNavigate('m4')} />}
        {masterScreen === 'm6' && <MicrolessonManagerView />}
        {masterScreen === 'm8' && <ClientManagerView />}
      </main>
    </div>
  );
}
