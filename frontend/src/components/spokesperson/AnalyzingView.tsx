'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionService, AzureReportResponse } from '../../services/sessionService';

interface AnalyzingViewProps {
  onNavigate: (screen: VoceroScreen) => void;
  sessionId?: string;
  onReportReady?: (report: AzureReportResponse) => void;
}

export const AnalyzingView: React.FC<AnalyzingViewProps> = ({
  onNavigate,
  sessionId = 'session-e2e-final-002',
  onReportReady
}) => {
  const { t } = useI18n();
  const d = t.L.u5;

  const [isCompleted, setIsCompleted] = useState(false);
  const [step1Done, setStep1Done] = useState(true);
  const [step2Done, setStep2Done] = useState(false);
  const [step3Done, setStep3Done] = useState(false);
  const [step4Done, setStep4Done] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const completedRef = useRef(false);
  const pollCountRef = useRef(0);

  // Formato mm:ss para el cronómetro
  const formatTime = (totalSec: number): string => {
    const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
    const s = (totalSec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  // Cronómetro independiente: avanza cada segundo hasta que se completa el análisis
  useEffect(() => {
    const timer = setInterval(() => {
      if (!completedRef.current) {
        setElapsedSeconds((prev) => prev + 1);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Polling al backend para verificar el estado real del análisis
  const checkStatus = useCallback(async () => {
    try {
      const raw = await sessionService.getRawReport(sessionId);
      pollCountRef.current += 1;

      if (raw && (raw.status === 'completed' || raw.puntuacion_global)) {
        setStep1Done(true);
        setStep2Done(true);
        setStep3Done(true);
        setStep4Done(true);
        setIsCompleted(true);
        completedRef.current = true;
        if (onReportReady) {
          onReportReady(raw);
        }
        return true; // Señal para detener el polling
      }

      // Avance visual progresivo basado en intentos reales (sin forzar completado)
      if (pollCountRef.current >= 2) setStep2Done(true);
      if (pollCountRef.current >= 4) setStep3Done(true);
      return false;
    } catch {
      pollCountRef.current += 1;
      // En caso de error, solo avanzar pasos visuales — NUNCA forzar completado
      if (pollCountRef.current >= 2) setStep2Done(true);
      if (pollCountRef.current >= 4) setStep3Done(true);
      return false;
    }
  }, [sessionId, onReportReady]);

  useEffect(() => {
    let cancelled = false;

    // Ejecutar polling cada 5 segundos
    const interval = setInterval(async () => {
      if (cancelled || completedRef.current) return;
      const done = await checkStatus();
      if (done && interval) clearInterval(interval);
    }, 5000);

    // Primera verificación inmediata
    checkStatus();

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkStatus]);

  // Estilo compartido para la etiqueta de estado (nunca se parte en dos líneas)
  const statusLabelStyle: React.CSSProperties = {
    whiteSpace: 'nowrap',
    flexShrink: 0,
    marginLeft: '12px'
  };

  return (
    <div className="canvas-content">
      <div
        className="card"
        style={{
          textAlign: 'center',
          padding: '48px 32px',
          maxWidth: '680px',
          margin: '0 auto',
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        <div
          className="ph"
          style={{
            height: '70px',
            width: '70px',
            borderRadius: '50%',
            margin: '0 auto 20px',
            fontSize: '32px',
            background: isCompleted ? 'rgba(16, 185, 129, 0.15)' : 'var(--soft)',
            borderColor: isCompleted ? '#10b981' : 'var(--line)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          {isCompleted ? '✅' : '⚡'}
        </div>

        <h3
          style={{
            fontSize: '19px',
            fontWeight: 700,
            marginBottom: '6px',
            color: 'var(--ink)'
          }}
        >
          {isCompleted ? 'Evaluación Multimodal Finalizada' : d.head}
        </h3>
        <p style={{ fontSize: '13.5px', color: 'var(--muted)', marginBottom: '8px' }}>
          {isCompleted
            ? `¡Evaluación completada en ${formatTime(elapsedSeconds)}!`
            : `Generando evaluación en tiempo real... (${formatTime(elapsedSeconds)} transcurridos)`}
        </p>
        <div style={{ fontSize: '11.5px', color: 'var(--muted)', marginBottom: '24px' }}>
          Sesión: <code style={{ color: 'var(--accent2)' }}>{sessionId}</code>
        </div>

        <div
          style={{
            maxWidth: '460px',
            margin: '0 auto',
            textAlign: 'left',
            background: 'var(--soft)',
            padding: '18px 22px',
            borderRadius: '10px',
            border: '1px solid var(--line)'
          }}
        >
          {/* Paso 1: Subida de la grabación */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>☁️ Subida de la grabación</span>
            <span style={{ color: 'var(--success)', fontWeight: 700, ...statusLabelStyle }}>✓ Completado</span>
          </div>

          {/* Paso 2: Transcripción de la grabación */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>🎙️ Transcripción de la grabación</span>
            {step2Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700, ...statusLabelStyle }}>✓ Completado</span>
            ) : (
              <span style={{ color: 'var(--accent2)', fontWeight: 600, ...statusLabelStyle }}>Procesando...</span>
            )}
          </div>

          {/* Paso 3: Análisis de la grabación */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>📊 Análisis de la grabación</span>
            {step3Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700, ...statusLabelStyle }}>✓ Completado</span>
            ) : step2Done ? (
              <span style={{ color: 'var(--accent2)', fontWeight: 600, ...statusLabelStyle }}>Analizando...</span>
            ) : (
              <span style={{ color: 'var(--muted)', ...statusLabelStyle }}>En espera</span>
            )}
          </div>

          {/* Paso 4: Análisis de la voz y reporte final */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px'
            }}
          >
            <span>🧠 Análisis de la voz y reporte final</span>
            {step4Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700, ...statusLabelStyle }}>✓ Listo</span>
            ) : step3Done ? (
              <span style={{ color: 'var(--accent2)', fontWeight: 600, ...statusLabelStyle }}>Generando veredicto...</span>
            ) : (
              <span style={{ color: 'var(--muted)', ...statusLabelStyle }}>En espera</span>
            )}
          </div>
        </div>

        <div style={{ marginTop: '28px' }}>
          <button
            type="button"
            className="btn pri"
            disabled={!isCompleted}
            style={{
              padding: '12px 28px',
              fontSize: '14px',
              fontWeight: 600,
              background: isCompleted ? '#10b981' : '#94a3b8',
              borderColor: isCompleted ? '#059669' : '#94a3b8',
              color: '#fff',
              cursor: isCompleted ? 'pointer' : 'not-allowed',
              opacity: isCompleted ? 1 : 0.8,
              transition: 'all 0.3s ease'
            }}
            onClick={() => {
              if (isCompleted) onNavigate('u6');
            }}
          >
            {isCompleted ? 'Ver Reporte de IA del Coach ➔' : '⏳ Preparando informe... por favor espere'}
          </button>
        </div>
      </div>
    </div>
  );
};
