'use client';

import type { ReactNode } from 'react';
import Image from 'next/image';
import { LogOut } from 'lucide-react';
import logo from '../../../public/VoxReady_logo.png';
import styles from './PlatformHeader.module.css';

interface PlatformHeaderProps {
  badge?: string;
  navigation: ReactNode;
  navigationLabel: string;
  user: { displayName: string; initials: string };
  roleLabel: string;
  avatarTone?: 'brand' | 'client';
  onHome: () => void;
  onLogout: () => void;
}

export function PlatformHeader({ badge, navigation, navigationLabel, user, roleLabel, avatarTone = 'brand', onHome, onLogout }: PlatformHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.identity}>
        <button type="button" className={styles.brand} onClick={onHome} aria-label="VoxReady: ir al inicio">
          <Image src={logo} alt="VoxReady" className={styles.logo} />
        </button>
        {badge && <span className={styles.badge} title={badge}>{badge}</span>}
      </div>
      <nav className={styles.navigation} aria-label={navigationLabel}>{navigation}</nav>
      <div className={styles.account}>
        <span className={styles.avatar} data-tone={avatarTone} aria-hidden="true">{user.initials}</span>
        <div className={styles.user}>
          <span className={styles.name} title={user.displayName}>{user.displayName}</span>
          <span className={styles.role}>{roleLabel}</span>
        </div>
        <button type="button" className={styles.logout} onClick={onLogout}>
          <LogOut size={16} aria-hidden="true" />
          <span>Cerrar sesión</span>
        </button>
      </div>
    </header>
  );
}
