'use client';

import type { LucideIcon } from 'lucide-react';
import styles from './SectionNavigation.module.css';

export interface SectionNavigationItem<Screen extends string> {
  id: Screen;
  label: string;
  icon: LucideIcon;
}

interface SectionNavigationProps<Screen extends string> {
  items: readonly SectionNavigationItem<Screen>[];
  activeScreen: Screen;
  onNavigate: (screen: Screen) => void;
}

export function SectionNavigation<Screen extends string>({ items, activeScreen, onNavigate }: SectionNavigationProps<Screen>) {
  return (
    <div className={styles.sections}>
      {items.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" className={styles.tab}
          aria-current={activeScreen === id ? 'page' : undefined} onClick={() => onNavigate(id)}>
          <Icon size={18} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
