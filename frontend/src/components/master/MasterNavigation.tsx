'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { BookOpen, Building2, ChartNoAxesCombined, ChevronDown, ClipboardCheck, Layers, LayoutDashboard, ListChecks, PencilLine, Target, type LucideIcon } from 'lucide-react';
import type { MasterScreen } from './MasterDashboard';
import { useI18n } from '../../context/I18nContext';
import styles from './MasterNavigation.module.css';

interface MasterNavigationProps {
  activeScreen: MasterScreen;
  labelingEnabled: boolean;
  onNavigate: (screen: MasterScreen) => void;
}

interface NavigationItem {
  id: MasterScreen;
  label: string;
  description: string;
  icon: LucideIcon;
}

export function MasterNavigation({ activeScreen, labelingEnabled, onNavigate }: MasterNavigationProps) {
  const { t } = useI18n();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const groups: { id: string; label: string; icon: LucideIcon; items: NavigationItem[] }[] = [
    {
      id: 'evaluation', label: 'Evaluación', icon: ClipboardCheck,
      items: [
        { id: 'm2', label: 'Editor de Rúbrica', description: 'Define criterios de evaluación', icon: ListChecks },
        { id: 'm7', label: 'Editor de métricas', description: 'Configura indicadores y pesos', icon: ChartNoAxesCombined },
        ...(labelingEnabled ? [{ id: 'm3' as const, label: 'Cola de Etiquetado', description: 'Revisa casos pendientes', icon: Target }] : []),
      ],
    },
    {
      id: 'content', label: 'Contenidos', icon: Layers,
      items: [
        { id: 'm4', label: t.masterTopics.catalog, description: 'Explora temas y escenarios', icon: BookOpen },
        { id: 'm5', label: t.masterTopics.editor, description: 'Crea y ajusta contenidos', icon: PencilLine },
        { id: 'm6', label: 'Microlecciones', description: 'Gestiona contenidos de aprendizaje', icon: BookOpen },
      ],
    },
  ];

  useEffect(() => {
    if (!openGroup) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpenGroup(null);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [openGroup]);

  const navigate = (screen: MasterScreen) => {
    setOpenGroup(null);
    onNavigate(screen);
  };

  return (
    <div ref={rootRef} className={styles.navigation} onKeyDown={event => {
      if (event.key === 'Escape' && openGroup) {
        event.preventDefault();
        rootRef.current?.querySelector<HTMLButtonElement>(`[data-trigger="${openGroup}"]`)?.focus();
        setOpenGroup(null);
      }
    }}>
      <button type="button" className={styles.tab} aria-current={activeScreen === 'm1' ? 'page' : undefined} onClick={() => navigate('m1')}>
        <LayoutDashboard size={18} aria-hidden="true" /><span>Panel Maestro</span>
      </button>
      {groups.map(group => {
        const Icon = group.icon;
        const open = openGroup === group.id;
        const active = group.items.some(item => item.id === activeScreen);
        return (
          <div key={group.id} className={styles.group}
            onPointerEnter={event => { if (event.pointerType === 'mouse') setOpenGroup(group.id); }}
            onPointerLeave={event => {
              if (event.pointerType === 'mouse' && !event.currentTarget.querySelector(`.${styles.panel}`)?.contains(document.activeElement)) setOpenGroup(null);
            }}
            onBlur={event => {
              if (!event.currentTarget.contains(event.relatedTarget)) setOpenGroup(current => current === group.id ? null : current);
            }}>
            <button type="button" className={styles.tab} data-trigger={group.id} data-active={active || undefined}
              aria-expanded={open} aria-controls={`${id}-${group.id}`} id={`${id}-${group.id}-trigger`}
              onClick={() => setOpenGroup(current => current === group.id ? null : group.id)}>
              <Icon size={18} aria-hidden="true" /><span>{group.label}</span>
              <ChevronDown size={14} className={styles.chevron} aria-hidden="true" />
            </button>
            <div className={styles.dropdown} hidden={!open}>
              <ul className={styles.panel} id={`${id}-${group.id}`} aria-labelledby={`${id}-${group.id}-trigger`}>
                {group.items.map(item => {
                  const ItemIcon = item.icon;
                  return (
                    <li key={item.id}>
                      <button type="button" className={styles.option} aria-current={activeScreen === item.id ? 'page' : undefined}
                        onClick={() => {
                          rootRef.current?.querySelector<HTMLButtonElement>(`[data-trigger="${group.id}"]`)?.focus();
                          navigate(item.id);
                        }}>
                        <span className={styles.icon}><ItemIcon size={22} aria-hidden="true" /></span>
                        <span className={styles.text}><span className={styles.title}>{item.label}</span><span className={styles.description}>{item.description}</span></span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        );
      })}
      <button type="button" className={styles.tab} aria-current={activeScreen === 'm8' ? 'page' : undefined} onClick={() => navigate('m8')}>
        <Building2 size={18} aria-hidden="true" /><span>Clientes</span>
      </button>
    </div>
  );
}
