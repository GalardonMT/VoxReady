'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import { BookOpen, ChartNoAxesCombined, LayoutDashboard, Users } from 'lucide-react';
import { PlatformHeader } from '../common/PlatformHeader';
import { SectionNavigation, type SectionNavigationItem } from '../common/SectionNavigation';

export type ClientAdminScreen = 'a1' | 'a2' | 'a4' | 'a5';

const navItems: SectionNavigationItem<ClientAdminScreen>[] = [
  { id: 'a1', label: 'Panel del Cliente', icon: LayoutDashboard },
  { id: 'a2', label: 'Voceros', icon: Users },
  { id: 'a4', label: 'Escenarios', icon: BookOpen },
  { id: 'a5', label: 'Actividad', icon: ChartNoAxesCombined },
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
    <PlatformHeader
      badge={user.clientName || 'Cliente'}
      navigationLabel="Navegación del cliente"
      navigation={<SectionNavigation items={navItems} activeScreen={activeScreen} onNavigate={onNavigate} />}
      user={user}
      roleLabel="Admin del cliente"
      avatarTone="client"
      onHome={() => onNavigate('a1')}
      onLogout={() => {
        logout();
        router.push('/login');
      }}
    />
  );
};
