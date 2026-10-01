'use client';

import React, { useEffect, useState } from 'react';
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

  const [pollCount, setPollCount] = useState(0);
  const [isCompleted, setIsCompleted] = useState(false);
  const [step1Done, setStep1Done] = useState(true);
  const [step2Done, setStep2Done] = useState(false);
  const [step3Done, setStep3Done] = useState(false);
  const [step4Done, setStep4Done] = useState(false);
  const [statusText, setStatusText] = useState('Conectando con la cola de inferencia...');

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    let cancelled = false;

    async function checkStatus() {
      try {
        const raw = await sessionService.getRawReport(sessionId);
        if (cancelled) return;

        setPollCount((prev) => prev + 1);

        if (raw && (raw.status === 'completed' || raw.puntuacion_global)) {
          setStep1Done(true);
          setStep2Done(true);
          setStep3Done(true);
          setStep4Done(true);
          setIsCompleted(true);
          setStatusText('¡Evaluación multimodal completada con éxito por NVIDIA & MediaPipe!');
          if (onReportReady) {
            onReportReady(raw);
          }
          if (interval) clearInterval(interval);
          return;
        }

        // Simulación progresiva de pasos si está en procesamiento
        if (pollCount >= 1) setStep2Done(true);
        if (pollCount >= 2) setStep3Done(true);
        setStatusText(`Procesando en Azure Container Apps (intento #${pollCount + 1})...`);
      } catch (err) {
        if (!cancelled) {
          setPollCount((prev) => prev + 1);
          // Si el backend no tiene la sesión aún, mostrar avance visual
          if (pollCount >= 1) setStep2Done(true);
          if (pollCount >= 2) setStep3Done(true);
          if (pollCount >= 3) {
            setStep4Done(true);
            setIsCompleted(true);
          }
        }
      }
    }

    checkStatus();
    interval = setInterval(checkStatus, 3500);

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [sessionId, pollCount]);

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
          {statusText}
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
          {/* Step 1: FFmpeg */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>🎬 Separación FFmpeg (Audio PCM 16kHz & Frames)</span>
            <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
          </div>

          {/* Step 2: Audio/ASR */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>🎙️ ASR Parakeet & Métricas Acústicas (WPM, Muletillas)</span>
            {step2Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
            ) : (
              <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Procesando...</span>
            )}
          </div>

          {/* Step 3: MediaPipe Vision */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px',
              marginBottom: '12px'
            }}
          >
            <span>👁️ Análisis Visual MediaPipe (ca-vision-service)</span>
            {step3Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Completado</span>
            ) : step2Done ? (
              <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Analizando frames...</span>
            ) : (
              <span style={{ color: 'var(--muted)' }}>En espera</span>
            )}
          </div>

          {/* Step 4: NVIDIA LLM Judge */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '13px'
            }}
          >
            <span>🧠 Juez de Crisis NVIDIA Llama 3.2 90B & Fusión</span>
            {step4Done ? (
              <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ Listo</span>
            ) : step3Done ? (
              <span style={{ color: 'var(--accent2)', fontWeight: 600 }}>Generando veredicto...</span>
            ) : (
              <span style={{ color: 'var(--muted)' }}>En espera</span>
            )}
          </div>
        </div>

        <div style={{ marginTop: '28px' }}>
          <button
            type="button"
            className="btn pri"
            style={{
              padding: '12px 28px',
              fontSize: '14px',
              fontWeight: 600,
              background: isCompleted ? '#10b981' : 'var(--accent)',
              borderColor: isCompleted ? '#059669' : 'var(--accent)'
            }}
            onClick={() => onNavigate('u6')}
          >
            {isCompleted ? 'Ver Reporte de IA del Coach ➔' : d.viewReport}
          </button>
        </div>
      </div>
    </div>
  );
};
