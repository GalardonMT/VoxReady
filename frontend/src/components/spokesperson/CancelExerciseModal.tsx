'use client';

import React, { useEffect } from 'react';

export type CancelModalReason = 'manual' | 'tab_switch' | 'nav_leave';

export interface CancelExerciseModalProps {
  isOpen: boolean;
  reason?: CancelModalReason;
  title?: string;
  description?: string;
  continueText?: string;
  cancelText?: string;
  onContinue: () => void;
  onConfirmCancel: () => void;
}

export const CancelExerciseModal: React.FC<CancelExerciseModalProps> = ({
  isOpen,
  reason = 'manual',
  title,
  description,
  continueText,
  cancelText,
  onContinue,
  onConfirmCancel
}) => {
  // Manejo de la tecla Escape para continuar/cerrar de forma segura
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onContinue();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onContinue]);

  if (!isOpen) return null;

  // Textos adaptativos según el motivo
  let defaultTitle = '¿Deseas cancelar la ejercitación?';
  let defaultDesc =
    'Estás a punto de cancelar tu ejercitación. Si cancelas ahora, la grabación en curso se descartará por completo y no se guardará ningún progreso ni se enviará nada a la base de datos.';
  let badgeText = '🔒 Privacidad: Ningún registro ni video será almacenado en la base de datos.';

  if (reason === 'tab_switch') {
    defaultTitle = '⚠️ Ejercitación pausada por cambio de pestaña';
    defaultDesc =
      'Detectamos que saliste de la pestaña durante la ejercitación. Para garantizar la concentración y la validez de la evaluación, la sesión fue pausada. Si decides cancelar, nada se enviará a la base de datos.';
    badgeText = '⏸️ La grabación está en pausa. Puedes continuar cuando estés listo.';
  } else if (reason === 'nav_leave') {
    defaultTitle = '¿Salir y cancelar la ejercitación?';
    defaultDesc =
      'Tienes una ejercitación en curso. Si sales a otra sección de la plataforma, la práctica se cancelará y ningún progreso ni grabación se guardará en la base de datos.';
    badgeText = '⚠️ Salir ahora descartará todo el avance de esta sesión.';
  }

  const finalTitle = title || defaultTitle;
  const finalDesc = description || defaultDesc;
  const finalContinueText = continueText || 'Continuar ejercitación';
  const finalCancelText = cancelText || 'Cancelar ejercitación';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cancel-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(10, 15, 29, 0.82)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        animation: 'fadeIn 0.2s ease-out'
      }}
      onClick={onContinue}
    >
      <div
        style={{
          background: 'var(--panel)',
          color: 'var(--ink)',
          borderRadius: '16px',
          border: '1px solid var(--line)',
          maxWidth: '480px',
          width: '100%',
          padding: '28px 24px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.08)',
          textAlign: 'center',
          position: 'relative',
          animation: 'scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Icono de advertencia */}
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: reason === 'tab_switch' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            border: reason === 'tab_switch' ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(239, 68, 68, 0.4)',
            color: reason === 'tab_switch' ? '#f59e0b' : '#ef4444',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '26px',
            margin: '0 auto 16px auto'
          }}
        >
          {reason === 'tab_switch' ? '⏸️' : '⚠️'}
        </div>

        {/* Título */}
        <h3
          id="cancel-modal-title"
          style={{
            fontSize: '19px',
            fontWeight: 700,
            margin: '0 0 10px 0',
            lineHeight: 1.3
          }}
        >
          {finalTitle}
        </h3>

        {/* Descripción de impacto */}
        <p
          style={{
            fontSize: '13.5px',
            lineHeight: 1.55,
            color: 'var(--muted)',
            margin: '0 0 18px 0'
          }}
        >
          {finalDesc}
        </p>

        {/* Banner de Garantía / Estado */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            padding: '10px 14px',
            borderRadius: '10px',
            background: 'var(--soft)',
            border: '1px solid var(--line)',
            fontSize: '12px',
            fontWeight: 500,
            marginBottom: '24px',
            color: 'var(--ink)'
          }}
        >
          <span>{badgeText}</span>
        </div>

        {/* Acciones */}
        <div
          style={{
            display: 'flex',
            gap: '12px',
            justifyContent: 'center',
            flexWrap: 'wrap'
          }}
        >
          {/* Opción 1: Continuar (acción principal sugerida) */}
          <button
            type="button"
            className="btn pri"
            onClick={onContinue}
            style={{
              flex: '1 1 180px',
              padding: '11px 18px',
              fontSize: '13.5px',
              fontWeight: 600
            }}
          >
            ▶ {finalContinueText}
          </button>

          {/* Opción 2: Cancelar (acción destructiva, limpia sin guardar) */}
          <button
            type="button"
            className="btn ghost"
            onClick={onConfirmCancel}
            style={{
              flex: '1 1 180px',
              padding: '11px 18px',
              fontSize: '13.5px',
              fontWeight: 600,
              color: '#ef4444',
              borderColor: 'rgba(239, 68, 68, 0.45)',
              background: 'rgba(239, 68, 68, 0.08)'
            }}
          >
            ✕ {finalCancelText}
          </button>
        </div>
      </div>
    </div>
  );
};
