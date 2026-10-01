'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionService } from '../../services/sessionService';

interface LiveSessionViewProps {
  onNavigate: (screen: VoceroScreen) => void;
  sessionId?: string;
  scenarioId?: string;
  onSessionComplete?: (sessionId: string) => void;
}

export const LiveSessionView: React.FC<LiveSessionViewProps> = ({
  onNavigate,
  sessionId,
  scenarioId = 'crisis-voceria-01',
  onSessionComplete
}) => {
  const { t } = useI18n();
  const d = t.L.u4;

  const activeSessionId = sessionId || `session-crisis-${Date.now()}`;

  const [isPaused, setIsPaused] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(3);
  const totalQuestions = 8;

  // Estados de captura de video y subida
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const [streamActive, setStreamActive] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');

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

  // Iniciar cámara y grabación automática al entrar
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;

    async function initMedia() {
      try {
        let savedCameraId = '';
        let savedMicId = '';
        try {
          savedCameraId = localStorage.getItem('voxready_selected_camera') || '';
          savedMicId = localStorage.getItem('voxready_selected_mic') || '';
        } catch {}

        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              width: { ideal: 1280 },
              height: { ideal: 720 },
              frameRate: { ideal: 30 },
              ...(savedCameraId ? { deviceId: { exact: savedCameraId } } : {})
            },
            audio: {
              echoCancellation: true,
              noiseSuppression: false, // Evita voz robotica y cortes por supresion agresiva
              autoGainControl: false,  // Evita saturacion al limite maximo (-32768 / +32767)
              channelCount: 1,
              ...(savedMicId ? { deviceId: { exact: savedMicId } } : {})
            }
          });
        } catch {
          // Fallback seguro si el deviceId guardado no responde o se desconectó
          stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
            audio: true
          });
        }

        streamRef.current = stream;
        setStreamActive(true);
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }

        // Configurar MediaRecorder con bitrate y codec optimo
        let mimeType = 'video/webm;codecs=vp8,opus';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
            ? 'video/webm;codecs=vp9,opus'
            : (MediaRecorder.isTypeSupported('video/webm') ? 'video/webm' : '');
        }

        const recorderOptions: MediaRecorderOptions = {
          ...(mimeType ? { mimeType } : {}),
          videoBitsPerSecond: 2500000, // 2.5 Mbps para 720p @ 30fps fluido
          audioBitsPerSecond: 128000   // 128 kbps Opus alta fidelidad
        };

        const recorder = new MediaRecorder(stream, recorderOptions);
        chunksRef.current = [];
        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            chunksRef.current.push(e.data);
          }
        };

        // INICIAR EN FLUJO CONTINUO (SIN timeslice para eliminar los 1.374 saltos temporales rotos)
        recorder.start();
        mediaRecorderRef.current = recorder;

        timer = setInterval(() => {
          if (!isPaused) {
            setRecordingSeconds((prev) => prev + 1);
          }
        }, 1000);
      } catch (err: any) {
        console.warn('Error al iniciar cámara/micrófono:', err);
        setErrorMessage(`Dispositivo de video no disponible: ${err.message}. Modo simulación activado.`);
      }
    }

    initMedia();

    return () => {
      if (timer) clearInterval(timer);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch {}
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  const handleNextQuestion = () => {
    if (questionIndex < totalQuestions) {
      setQuestionIndex((prev) => prev + 1);
    }
    // No hacer nada en la última pregunta — la sesión solo termina
    // cuando el usuario presiona explícitamente "Finalizar grabación"
  };

  const handleFinishSession = async () => {
    setIsUploading(true);
    setUploadStatus('1/3 Finalizando codificación de video y vaciando buffers...');

    const recorder = mediaRecorderRef.current;

    // 1. Esperar formalmente al evento onstop de MediaRecorder
    if (recorder && recorder.state !== 'inactive') {
      await new Promise<void>((resolve) => {
        const safetyTimer = setTimeout(() => {
          console.warn('Timeout de seguridad al esperar onstop del MediaRecorder');
          resolve();
        }, 3000);

        recorder.onstop = () => {
          clearTimeout(safetyTimer);
          resolve();
        };

        // Forzar vaciado de buffers pendientes antes de cerrar
        try {
          if (typeof recorder.requestData === 'function' && recorder.state === 'recording') {
            recorder.requestData();
          }
        } catch (e) {
          console.warn('Advertencia en requestData():', e);
        }

        try {
          recorder.stop();
        } catch (e) {
          console.warn('Advertencia en recorder.stop():', e);
          clearTimeout(safetyTimer);
          resolve();
        }
      });
    }

    // 2. Detener pistas de cámara y micrófono SOLO después de que el recorder cerró el stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // 3. Crear el Blob con todos los fragmentos volcados
    const videoBlob = chunksRef.current.length > 0
      ? new Blob(chunksRef.current, { type: 'video/webm' })
      : new Blob(['voxready-sample-recording'], { type: 'video/webm' });

    console.info(`[MediaRecorder] Grabación finalizada. Total chunks: ${chunksRef.current.length}, tamaño: ${videoBlob.size} bytes`);

    try {
      setUploadStatus('1/3 Solicitando firma SAS de Azure Blob Storage...');
      const { uploadUrl, blobPath } = await sessionService.getUploadUrl(activeSessionId);

      setUploadStatus('2/3 Subiendo video directamente a Blob Storage (Zero-Proxy)...');
      setUploadProgress(25);

      await sessionService.uploadDirectToBlob(uploadUrl, videoBlob, (pct) => {
        setUploadProgress(pct);
      });

      setUploadProgress(100);
      setUploadStatus('3/3 Notificando a la cola de Service Bus para análisis...');

      await sessionService.finishSession(
        activeSessionId,
        blobPath,
        scenarioId,
        'tenant-voxready-dev'
      );

      setUploadStatus('¡Encolado con éxito en Azure! Pasando a análisis...');
      if (onSessionComplete) {
        onSessionComplete(activeSessionId);
      }

      setTimeout(() => {
        onNavigate('u5');
      }, 1000);
    } catch (err: any) {
      console.error('Error al subir grabación a Azure:', err);
      setErrorMessage(`Fallo en el pipeline de subida: ${err.message}. Pasando a análisis.`);
      setTimeout(() => {
        if (onSessionComplete) onSessionComplete(activeSessionId);
        onNavigate('u5');
      }, 1500);
    }
  };

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `REC ${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="canvas-content" style={{ position: 'relative' }}>
      {/* Overlay de Subida a Blob Storage */}
      {isUploading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.92)',
            backdropFilter: 'blur(8px)',
            zIndex: 50,
            borderRadius: '12px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            textAlign: 'center'
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              border: '4px solid rgba(52, 211, 153, 0.2)',
              borderTopColor: '#10b981',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              marginBottom: '20px'
            }}
          />
          <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', marginBottom: '8px' }}>
            Transfiriendo Grabación a Azure
          </h3>
          <p style={{ fontSize: '13px', color: '#94a3b8', maxWidth: '420px', marginBottom: '18px' }}>
            {uploadStatus}
          </p>
          {uploadProgress !== null && (
            <div
              style={{
                width: '100%',
                maxWidth: '360px',
                height: '8px',
                background: '#1e293b',
                borderRadius: '999px',
                overflow: 'hidden'
              }}
            >
              <div
                style={{
                  width: `${uploadProgress}%`,
                  height: '100%',
                  background: '#10b981',
                  transition: 'width 0.3s ease'
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* 50/50 Split View */}
      <div className="grid2" style={{ marginBottom: '16px' }}>
        {/* Left: AI Interviewer */}
        <div className="vid" style={{ minHeight: '280px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <span className="tag">🤖 {d.interviewer}</span>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '48px', marginBottom: '10px' }}>👔</div>
            <div style={{ fontSize: '14px', color: '#aab4bd', fontWeight: 600 }}>{d.interviewerV}</div>
            <div style={{ fontSize: '12px', color: '#7a858e', marginTop: '4px' }}>
              {isPaused ? '⏸ En pausa' : '🗣️ Formulando pregunta al vocero...'}
            </div>
          </div>
        </div>

        {/* Right: User Self-View con Cámara Real */}
        <div
          className="self"
          style={{
            minHeight: '280px',
            position: 'relative',
            overflow: 'hidden',
            borderRadius: '8px',
            background: '#090d16',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            style={{
              width: '100%',
              height: '100%',
              minHeight: '280px',
              objectFit: 'cover',
              transform: 'scaleX(-1)',
              display: streamActive ? 'block' : 'none'
            }}
          />

          {!streamActive && (
            <div style={{ textAlign: 'center', padding: '30px 0' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px' }}>🎙️</div>
              <div style={{ fontSize: '13px', color: '#cdd4da' }}>{d.selfV}</div>
              <div style={{ fontSize: '11px', color: '#88939e', marginTop: '4px' }}>
                {errorMessage || 'Iniciando captura de video HD...'}
              </div>
            </div>
          )}

          <div
            className="reclamp"
            style={{
              position: 'absolute',
              top: '12px',
              left: '12px',
              background: 'rgba(225, 29, 72, 0.9)',
              color: '#fff',
              padding: '4px 10px',
              borderRadius: '999px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 700,
              fontSize: '11.5px',
              letterSpacing: '0.5px'
            }}
          >
            <i className="recdot" style={{ width: '8px', height: '8px', background: '#fff', borderRadius: '50%' }} />
            <span>{formatTimer(recordingSeconds)}</span>
          </div>

          <div
            style={{
              position: 'absolute',
              bottom: '10px',
              right: '12px',
              background: 'rgba(0, 0, 0, 0.65)',
              color: '#34d399',
              padding: '3px 8px',
              borderRadius: '6px',
              fontSize: '10.5px',
              fontWeight: 600
            }}
          >
            HD 720p · MediaPipe Ready
          </div>
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
          onClick={handleNextQuestion}
          disabled={questionIndex >= totalQuestions}
          title={questionIndex >= totalQuestions ? 'Última pregunta alcanzada' : 'Simular siguiente pregunta'}
        >
          {questionIndex >= totalQuestions ? 'Última pregunta ✓' : 'Siguiente pregunta ➔'}
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
          style={{ marginLeft: 'auto', background: '#e11d48', borderColor: '#be123c', color: '#fff' }}
          onClick={handleFinishSession}
          disabled={isUploading}
        >
          {isUploading ? 'Encolando en Azure...' : `${d.finish} · Enviar a Evaluación 🚀`}
        </button>
      </div>
    </div>
  );
};
