'use client';

import React, { useEffect, useState } from 'react';
import { ProtectedRoute } from '../../../components/auth/ProtectedRoute';
import { ActivityUsageView } from '../../../components/client-admin/ActivityUsageView';
import {
  ClientAdminHeader,
  type ClientAdminScreen,
} from '../../../components/client-admin/ClientAdminHeader';
import { ClientDashboard } from '../../../components/client-admin/ClientDashboard';
import { ClientScenariosView } from '../../../components/client-admin/ClientScenariosView';
import { RetentionPolicyView } from '../../../components/client-admin/RetentionPolicyView';
import { SpokespersonListView } from '../../../components/client-admin/SpokespersonListView';

const CLIENT_ADMIN_SCREENS: ClientAdminScreen[] = ['a1', 'a2', 'a3', 'a4', 'a5'];

export default function AdminPage() {
  return (
    <ProtectedRoute allowedRoles={['client_admin']}>
      <AdminContent />
    </ProtectedRoute>
  );
}

function AdminContent() {
  const [adminScreen, setAdminScreen] = useState<ClientAdminScreen>('a1');

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('screen');
    if (requested && CLIENT_ADMIN_SCREENS.includes(requested as ClientAdminScreen)) {
      const timer = window.setTimeout(
        () => setAdminScreen(requested as ClientAdminScreen),
        0,
      );
      return () => window.clearTimeout(timer);
    }
  }, []);

  const handleAdminNavigate = (screen: ClientAdminScreen) => {
    setAdminScreen(screen);
    const url = new URL(window.location.href);
    url.searchParams.set('screen', screen);
    window.history.replaceState(null, '', `${url.pathname}${url.search}`);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="platform-container">
      <ClientAdminHeader activeScreen={adminScreen} onNavigate={handleAdminNavigate} />

      <main className="canvas">
        {adminScreen === 'a1' && <ClientDashboard />}
        {adminScreen === 'a2' && <SpokespersonListView />}
        {adminScreen === 'a3' && <RetentionPolicyView />}
        {adminScreen === 'a4' && <ClientScenariosView />}
        {adminScreen === 'a5' && <ActivityUsageView />}
      </main>
    </div>
  );
}
