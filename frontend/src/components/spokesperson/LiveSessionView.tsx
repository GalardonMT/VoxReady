'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface LiveSessionViewProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const LiveSessionView: React.FC<LiveSessionViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u4;

  const [isPaused, setIsPaused] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(3);
  const totalQuestions = 8;
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const [streamError, setStreamError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    let stream: MediaStream | null = null;
    
    async function setupCamera() {
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        if (!isMounted) {
          s.getTracks().forEach(track => track.stop());
          return;
        }
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
        }
      } catch (err: any) {
        if (isMounted) {
          setStreamError('Error al acceder a la cámara o micrófono: ' + err.message);
        }
      }
    }
    setupCamera();

    return () => {
      isMounted = false;
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, []);

  const questions = [
    '¿Cuál es la gravedad real de la falla detectada en el lote de producción?',
    '¿Cómo garantizan que otros productos en el mercado no estén afectados por el mismo problema?',
    d.qEx,
    '¿Qué compensación inmediata recibirán los clientes perjudicados?',
    '¿Existen sanciones internas contra los responsables de la supervisión de calidad?',
    '¿Cómo afectará este retiro las metas comerciales y financieras del trimestre?',
    '¿Qué medidas concretas han implementado para que esto no vuelva a ocurrir jamás?',
    'Para concluir, ¿cuál es el mensaje definitivo de la presidencia de la empresa a las familias?'
  ];

  const currentQuestion = questions[questionIndex - 1] || d.qEx;

  const handleNextQuestion = () => {
    if (questionIndex < totalQuestions) {
      setQuestionIndex((prev) => prev + 1);
    } else {
      onNavigate('u5');
    }
  };

  return (
    <div className="canvas-content">
      {/* 50/50 Split View */}
      <div className="grid2" style={{ marginBottom: '16px' }}>
        {/* Left: AI Interviewer */}
        <div className="vid" style={{ minHeight: '260px' }}>
          <span className="tag">🤖 {d.interviewer}</span>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '44px', marginBottom: '10px' }}>👔</div>
            <div style={{ fontSize: '13px', color: '#aab4bd' }}>{d.interviewerV}</div>
            <div style={{ fontSize: '11px', color: '#7a858e', marginTop: '4px' }}>
              {isPaused ? '⏸ En pausa' : '🗣️ Formulando pregunta...'}
            </div>
          </div>
        </div>

        {/* Right: User Self-View */}
        <div className="self" style={{ minHeight: '260px', position: 'relative', overflow: 'hidden' }}>
          <video 
            ref={videoRef} 
            autoPlay 
            muted 
            playsInline 
            style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', top: 0, left: 0 }} 
          />
          {streamError && (
            <div style={{ position: 'absolute', top: '10px', left: '10px', background: 'rgba(255,0,0,0.7)', color: 'white', padding: '4px 8px', borderRadius: '4px', fontSize: '12px', zIndex: 10 }}>
              {streamError}
            </div>
          )}
          <div className="reclamp" style={{ position: 'absolute', top: '10px', left: '10px', zIndex: 10 }}>
            <i className="recdot" />
            <span>REC 02:14</span>
          </div>
          {!streamError && (
            <div style={{ position: 'absolute', bottom: '10px', width: '100%', textAlign: 'center', zIndex: 10 }}>
              <div style={{ display: 'inline-block', background: 'rgba(0,0,0,0.5)', padding: '4px 10px', borderRadius: '20px' }}>
                <div style={{ fontSize: '11px', color: '#fff' }}>
                  Encuadre: Óptimo · Audio: Capturando
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Live Question Card */}
      <div
        className="card"
        style={{
          marginBottom: '16px',
          borderLeft: '4px solid var(--accent2)',
          background: 'var(--panel)'
        }}
      >
        <div className="label">{d.qL}</div>
        <div
          style={{
            fontSize: '17px',
            lineHeight: 1.5,
            color: 'var(--ink)',
            fontWeight: 500,
            marginTop: '4px'
          }}
        >
          “{currentQuestion}”
        </div>
      </div>

      {/* Control Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          flexWrap: 'wrap',
          padding: '12px 16px',
          borderRadius: '8px',
          background: 'var(--panel)',
          border: '1px solid var(--line)'
        }}
      >
        <button
          type="button"
          className="btn"
          onClick={() => setIsPaused((prev) => !prev)}
        >
          {isPaused ? d.resume : d.pause}
        </button>

        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            // trigger small visual indication
          }}
        >
          {d.repeat}
        </button>

        <button
          type="button"
          className="btn ghost"
          onClick={handleNextQuestion}
          title="Simular siguiente pregunta"
        >
          Siguiente pregunta ⏩
        </button>

        <div className="meter col" style={{ maxWidth: '240px' }}>
          <i
            style={{
              width: `${(questionIndex / totalQuestions) * 100}%`,
              background: 'var(--accent)'
            }}
          />
        </div>

        <span style={{ fontSize: '12.5px', color: 'var(--muted)', fontWeight: 500 }}>
          Pregunta {questionIndex} de {totalQuestions}
        </span>

        <button
          type="button"
          className="btn pri"
          style={{ marginLeft: 'auto' }}
          onClick={() => onNavigate('u5')}
        >
          {d.finish} ⏹️
        </button>
      </div>
    </div>
  );
};
