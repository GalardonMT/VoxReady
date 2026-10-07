'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionService, type QuestionMark } from '../../services/sessionService';
import type { SessionSetup } from '../../services/sessionFlowService';
import { InterviewerAvatar } from './InterviewerAvatar';
import { CancelExerciseModal, type CancelModalReason } from './CancelExerciseModal';

// Subcomponente accesible para la subida
interface UploadOverlayProps {
  isUploading: boolean;
  uploadStatus: string;
  uploadProgress: number | null;
  title?: string;
}

export const UploadOverlay: React.FC<UploadOverlayProps> = ({
  isUploading,
  uploadStatus,
  uploadProgress,
  title = 'Procesando tu sesión'
}) => {
  if (!isUploading) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-busy="true"
      aria-label={title}
      className="upload-overlay-backdrop"
    >
      <div className="upload-overlay-spinner" />
      <h3 className="upload-overlay-title">
        {title}
      </h3>
      <p className="upload-overlay-status">
        {uploadStatus}
      </p>
      <div className="upload-overlay-bar-track">
        <div
          className="upload-overlay-bar-fill"
          style={{
            width: uploadProgress !== null ? `${uploadProgress}%` : '40%',
            opacity: uploadProgress !== null ? 1 : 0.6,
            animation: uploadProgress === null ? 'pulse-red 1.5s infinite' : undefined
          }}
        />
      </div>
    </div>
  );
};

interface LiveSessionViewProps {
  onNavigate: (screen: VoceroScreen) => void;
  sessionId?: string;
  scenarioId?: string;
  tenantId?: string;
  setup?: SessionSetup;
  onSessionComplete?: (sessionId: string) => void;
  onCancel?: () => void;
}

export const LiveSessionView: React.FC<LiveSessionViewProps> = ({
  onNavigate,
  sessionId,
  scenarioId = 'crisis-voceria-01',
  tenantId,
  setup,
  onSessionComplete,
  onCancel
}) => {
  const { t } = useI18n();
  const d = t.L.u4;
  const { user } = useAuth();

  const effectiveTenantId = tenantId || user?.clientId || 'tenant-voxready-dev';

  const [generatedSessionId] = useState(() => `session-crisis-${Date.now()}`);
  const activeSessionId = sessionId || setup?.sessionId || generatedSessionId;
  const activeScenarioId = scenarioId || setup?.scenarioId || 'crisis-voceria-01';

  const defaultQuestions = [
    '¿Cuál es la gravedad real de la falla detectada en el lote de producción?',
    '¿Cómo garantizan que otros productos en el mercado no estén afectados por el mismo problema?',
    d.qEx,
    '¿Qué compensación inmediata recibirán los clientes perjudicados?',
    '¿Existen sanciones internas contra los responsables de la supervisión de calidad?',
    '¿Cómo afectará este retiro las metas comerciales y financieras del trimestre?',
    '¿Qué medidas concretas han implementado para que esto no vuelva a ocurrir jamás?',
    'Para concluir, ¿cuál es el mensaje definitivo de la presidencia de la empresa a las familias?'
  ];

  const questions = (setup?.questions && setup.questions.length > 0)
    ? setup.questions.map((q) => q.text)
    : defaultQuestions;

  const [isPaused, setIsPaused] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(1);
  const [isUserTurn, setIsUserTurn] = useState(false);
  const totalQuestions = questions.length;

  // Estados de captura de video y subida
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const pendingBlobRef = useRef<Blob | null>(null);

  const [streamActive, setStreamActive] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');

  // Control de timers y montaje
  const isMountedRef = useRef(true);
  const navTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const safetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Timer preciso con performance.now() excluyendo pausas
  const accumulatedMsRef = useRef(0);
  const lastResumeRef = useRef<number | null>(null);

  const getElapsedMs = useCallback(() => {
    return (
      accumulatedMsRef.current +
      (lastResumeRef.current !== null ? performance.now() - lastResumeRef.current : 0)
    );
  }, []);

  // Timestamps de preguntas
  const marksRef = useRef<QuestionMark[]>([]);

  // Estados de control de cancelación y modal
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelModalReason, setCancelModalReason] = useState<CancelModalReason>('manual');
  const wasPausedRef = useRef(false);

  const currentQuestion = questions[questionIndex - 1] || questions[0] || d.qEx;

  // Limpieza al desmontar
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (navTimerRef.current) clearTimeout(navTimerRef.current);
      if (safetyTimerRef.current) clearTimeout(safetyTimerRef.current);
    };
  }, []);

  // Iniciar cámara y grabación automática al entrar
  useEffect(() => {
    let isCancelled = false;

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
              noiseSuppression: false, // Evita voz robótica y cortes por supresión agresiva
              autoGainControl: false,  // Evita saturación al límite máximo (-32768 / +32767)
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

        if (isCancelled || !isMountedRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        // Detectar desconexión de dispositivos durante la grabación
        stream.getTracks().forEach((track) => {
          track.onended = () => {
            if (!isMountedRef.current) return;
            setIsPaused(true);
            setErrorMessage(
              track.kind === 'video'
                ? (d.deviceVideoLost || 'Se perdió la conexión con la cámara.')
                : (d.deviceAudioLost || 'Se perdió la conexión con el micrófono.')
            );
          };
        });

        streamRef.current = stream;
        setStreamActive(true);

        // Configurar MediaRecorder con detección de códec (WebM o MP4 para Safari)
        let mimeType = 'video/webm;codecs=vp8,opus';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          if (MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')) {
            mimeType = 'video/webm;codecs=vp9,opus';
          } else if (MediaRecorder.isTypeSupported('video/mp4;codecs=avc1,mp4a.40.2')) {
            mimeType = 'video/mp4;codecs=avc1,mp4a.40.2';
          } else if (MediaRecorder.isTypeSupported('video/mp4')) {
            mimeType = 'video/mp4';
          } else if (MediaRecorder.isTypeSupported('video/webm')) {
            mimeType = 'video/webm';
          } else {
            mimeType = '';
          }
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

        // INICIAR EN FLUJO CONTINUO
        recorder.start();
        mediaRecorderRef.current = recorder;

        // Iniciar marcas de tiempo de las preguntas
        marksRef.current = [{ questionIndex: 1, startMs: 0, endMs: null }];
      } catch (err: unknown) {
        if (!isMountedRef.current) return;
        const message = err instanceof Error ? err.message : String(err);
        console.warn('Error al iniciar cámara/micrófono:', err);
        setErrorMessage(`Dispositivo de video no disponible: ${message}. Modo simulación activado.`);
      }
    }

    initMedia();

    return () => {
      isCancelled = true;
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch {}
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };
  }, [d.deviceAudioLost, d.deviceVideoLost]);

  // Asignar stream al <video> cuando streamActive sea verdadero
  useEffect(() => {
    if (streamActive && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [streamActive]);

  // Temporizador de alta precisión con performance.now (excluyendo pausas)
  useEffect(() => {
    if (streamActive && !isPaused) {
      lastResumeRef.current = performance.now();
    } else if (lastResumeRef.current !== null) {
      accumulatedMsRef.current += performance.now() - lastResumeRef.current;
      lastResumeRef.current = null;
    }
  }, [streamActive, isPaused]);

  // Actualización periódica del segundero para la UI
  useEffect(() => {
    if (!streamActive || isPaused) return;

    const timer = setInterval(() => {
      setRecordingSeconds(Math.floor(getElapsedMs() / 1000));
    }, 250);

    return () => clearInterval(timer);
  }, [streamActive, isPaused, getElapsedMs]);

  // Sincronizar estado del MediaRecorder con pausa/reanudación
  useEffect(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;

    if (isPaused && recorder.state === 'recording') {
      try {
        recorder.pause();
      } catch (e) {
        console.warn('Advertencia al pausar MediaRecorder:', e);
      }
    } else if (!isPaused && recorder.state === 'paused') {
      try {
        recorder.resume();
      } catch (e) {
        console.warn('Advertencia al reanudar MediaRecorder:', e);
      }
    }
  }, [isPaused]);

  // Gestión de marcas de tiempo por pregunta
  const goToQuestion = (nextIndex: number) => {
    const now = getElapsedMs();
    const marks = marksRef.current;
    const last = marks[marks.length - 1];
    if (last && last.endMs === null) {
      last.endMs = now;
    }
    marks.push({ questionIndex: nextIndex, startMs: now, endMs: null });
    setQuestionIndex(nextIndex);
    setIsUserTurn(false);
  };

  const handlePrevQuestion = () => {
    if (questionIndex > 1) {
      goToQuestion(questionIndex - 1);
    }
  };

  const handleNextQuestion = () => {
    if (questionIndex < totalQuestions) {
      goToQuestion(questionIndex + 1);
    }
  };

  const closeMarks = (): QuestionMark[] => {
    const marks = marksRef.current;
    const last = marks[marks.length - 1];
    if (last && last.endMs === null) {
      last.endMs = getElapsedMs();
    }
    return marksRef.current;
  };

  // Apertura del modal de confirmación de cancelación (evita doble apertura)
  const handleOpenCancelModal = useCallback((reason: CancelModalReason = 'manual') => {
    if (isUploading || showCancelModal) return;
    wasPausedRef.current = isPaused;
    setIsPaused(true);
    setCancelModalReason(reason);
    setShowCancelModal(true);
  }, [isUploading, showCancelModal, isPaused]);

  const openModalRef = useRef(handleOpenCancelModal);
  openModalRef.current = handleOpenCancelModal;

  // Continuar la ejercitación (cerrar modal y restaurar estado de pausa)
  const handleContinueFromModal = () => {
    setShowCancelModal(false);
    if (!wasPausedRef.current) {
      setIsPaused(false);
    }
  };

  // Confirmar cancelación: descartar grabación y detener periféricos
  const handleConfirmCancel = () => {
    setShowCancelModal(false);

    // 1. Detener MediaRecorder y anular callback
    if (mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.ondataavailable = null;
        if (mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
      } catch (e) {
        console.warn('Advertencia al detener MediaRecorder en cancelación:', e);
      }
      mediaRecorderRef.current = null;
    }

    // 2. Vaciar chunks y referencias
    chunksRef.current = [];
    pendingBlobRef.current = null;

    // 3. Detener pistas de hardware
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setStreamActive(false);

    console.info('[LiveSessionView] Ejercitación cancelada por el usuario. Descartando sesión.');

    // 4. Notificar o regresar
    if (onCancel) {
      onCancel();
    } else {
      onNavigate('u2');
    }
  };

  // Detección de cambio de pestaña del navegador sin closures obsoletos
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && streamActive && !isUploading) {
        openModalRef.current('tab_switch');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [streamActive, isUploading]);

  // Advertencia antes de recargar o cerrar la página
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (streamActive && !isUploading) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [streamActive, isUploading]);

  // Pipeline de subida con soporte de reintento
  const uploadPipeline = async (blob: Blob) => {
    setUploadError(null);
    setIsUploading(true);
    setUploadProgress(null); // Progreso indeterminado inicial

    try {
      setUploadStatus(d.preparingUpload || 'Preparando la subida…');
      const ext = blob.type.includes('mp4') ? 'mp4' : 'webm';
      const { uploadUrl, blobPath } = await sessionService.getUploadUrl(activeSessionId, ext);

      setUploadStatus(d.uploading || 'Subiendo tu grabación…');
      await sessionService.uploadDirectToBlob(uploadUrl, blob, (pct) => {
        if (isMountedRef.current) {
          setUploadProgress(pct);
        }
      });

      setUploadStatus(d.preparingAnalysis || 'Preparando tu análisis…');
      await sessionService.finishSession(
        activeSessionId,
        blobPath,
        activeScenarioId,
        effectiveTenantId,
        closeMarks()
      );

      pendingBlobRef.current = null;
      if (onSessionComplete) {
        onSessionComplete(activeSessionId);
      }

      navTimerRef.current = setTimeout(() => {
        if (isMountedRef.current) {
          onNavigate('u5');
        }
      }, 800);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      console.error('Error al subir grabación:', err);
      if (isMountedRef.current) {
        setUploadError(message);
        setIsUploading(false); // Mantener el Blob en pendingBlobRef para reintentar
      }
    }
  };

  const handleRetryUpload = () => {
    if (pendingBlobRef.current) {
      uploadPipeline(pendingBlobRef.current);
    }
  };

  const handleDiscard = () => {
    pendingBlobRef.current = null;
    if (onCancel) {
      onCancel();
    } else {
      onNavigate('u2');
    }
  };

  // Finalizar sesión y detener grabadora
  const handleFinishSession = async () => {
    setUploadError(null);
    setIsUploading(true);
    setUploadProgress(null);
    setUploadStatus(d.finalizingRecording || 'Finalizando grabación…');

    const recorder = mediaRecorderRef.current;

    // 1. Esperar formalmente al evento onstop de MediaRecorder
    if (recorder && recorder.state !== 'inactive') {
      await new Promise<void>((resolve) => {
        const safetyTimer = setTimeout(() => {
          console.warn('Timeout de seguridad al esperar onstop del MediaRecorder');
          resolve();
        }, 3000);
        safetyTimerRef.current = safetyTimer;

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

    // 2. Detener pistas de periféricos
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setStreamActive(false);

    // 3. Validar chunks sin crear blobs falsos
    if (chunksRef.current.length === 0) {
      setIsUploading(false);
      setUploadError(d.noCapture || 'No se capturó ningún video. Revisa tu cámara y micrófono.');
      return;
    }

    // 4. Crear el Blob con el mimeType real
    const type = recorder?.mimeType || 'video/webm';
    const videoBlob = new Blob(chunksRef.current, { type });
    pendingBlobRef.current = videoBlob;

    console.info(`[MediaRecorder] Grabación finalizada. Total chunks: ${chunksRef.current.length}, tamaño: ${videoBlob.size} bytes, tipo: ${type}`);

    await uploadPipeline(videoBlob);
  };

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `REC ${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="canvas-content" style={{ position: 'relative' }}>
      {/* Subcomponente Overlay de Subida */}
      <UploadOverlay
        isUploading={isUploading}
        uploadStatus={uploadStatus}
        uploadProgress={uploadProgress}
        title={d.uploadTitle || 'Procesando tu sesión'}
      />

      {/* Banner de error de subida con opciones de reintento o descarte */}
      {uploadError && (
        <div role="alert" className="upload-error-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '20px' }}>⚠️</span>
            <div>
              <div style={{ fontWeight: 700, color: '#ef4444', fontSize: '13.5px' }}>
                {d.uploadFailed || 'No pudimos subir tu grabación.'}
              </div>
              <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                {uploadError}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              className="btn pri"
              style={{ padding: '6px 14px', fontSize: '12px' }}
              onClick={handleRetryUpload}
              aria-label={d.retry || 'Reintentar subida'}
            >
              🔄 {d.retry || 'Reintentar'}
            </button>
            <button
              type="button"
              className="btn ghost"
              style={{ padding: '6px 14px', fontSize: '12px', color: '#cbd5e1' }}
              onClick={handleDiscard}
              aria-label={d.discard || 'Descartar grabación'}
            >
              {d.discard || 'Descartar'}
            </button>
          </div>
        </div>
      )}

      {/* 50/50 Split View */}
      <div className="grid2" style={{ marginBottom: '16px' }}>
        {/* Left: AI Interviewer */}
        <div
          className="vid"
          style={{
            minHeight: '280px',
            position: 'relative',
            padding: 0,
            overflow: 'hidden',
            borderRadius: '8px',
            background: '#090d16',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          }}
        >
          <InterviewerAvatar
            questionText={currentQuestion}
            questionIndex={questionIndex}
            isPaused={isPaused}
            onSpeechEnd={() => setIsUserTurn(true)}
          />
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
              display: streamActive ? 'block' : 'none',
              filter: isPaused ? 'brightness(0.6)' : 'none',
              transition: 'filter 0.3s ease'
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

          {/* Overlay de Pausa sobre la cámara del usuario */}
          {isPaused && (
            <div className="pause-cam-overlay" aria-label="Cámara en pausa">
              <div className="pause-cam-icon">
                <svg
                  width="26"
                  height="26"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  style={{ display: 'block' }}
                >
                  <rect x="6" y="4" width="4.5" height="16" rx="2" />
                  <rect x="13.5" y="4" width="4.5" height="16" rx="2" />
                </svg>
              </div>
              <span className="pause-cam-badge">
                {d.pausedStatus || 'En pausa'}
              </span>
            </div>
          )}

          <div
            className="reclamp"
            role="status"
            aria-live="polite"
            style={{
              position: 'absolute',
              top: '12px',
              left: '12px',
              background: isPaused ? 'rgba(234, 179, 8, 0.95)' : 'rgba(225, 29, 72, 0.9)',
              color: '#fff',
              padding: '4px 10px',
              borderRadius: '999px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 700,
              fontSize: '11.5px',
              letterSpacing: '0.5px',
              zIndex: 20,
              transition: 'background 0.3s ease'
            }}
          >
            <i
              className="recdot"
              style={{
                width: '8px',
                height: '8px',
                background: '#fff',
                borderRadius: '50%',
                animation: isPaused ? 'none' : undefined,
                opacity: isPaused ? 0.8 : 1
              }}
            />
            <span>{isPaused ? `PAUSA ${formatTimer(recordingSeconds).replace('REC ', '')}` : formatTimer(recordingSeconds)}</span>
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
              fontWeight: 600,
              zIndex: 20
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
          background: 'var(--panel)',
          position: 'relative'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div className="label">{d.qL}</div>
          {isUserTurn && !isPaused && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#10b981',
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                padding: '2px 8px',
                borderRadius: '999px',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                animation: 'pulse-red 2s infinite'
              }}
            >
              🎤 {d.yourTurn || 'Tu turno'}
            </span>
          )}
        </div>
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

      {/* Barra de Control */}
      <div className="live-session-controls">
        <button
          type="button"
          className="btn"
          onClick={() => setIsPaused((prev) => !prev)}
          aria-label={isPaused ? d.resume : d.pause}
        >
          {isPaused ? d.resume : d.pause}
        </button>

        <button
          type="button"
          className="btn ghost"
          onClick={handlePrevQuestion}
          disabled={questionIndex <= 1}
          aria-label={questionIndex <= 1 ? 'Primera pregunta' : (d.prevQ || 'Pregunta anterior')}
          title={questionIndex <= 1 ? 'Primera pregunta' : (d.prevQ || 'Pregunta anterior')}
        >
          ⬅ {d.prevQ || 'Anterior'}
        </button>

        <button
          type="button"
          className="btn ghost"
          onClick={handleNextQuestion}
          disabled={questionIndex >= totalQuestions}
          aria-label={questionIndex >= totalQuestions ? (d.lastQ || 'Última pregunta') : (d.nextQ || 'Siguiente pregunta')}
          title={questionIndex >= totalQuestions ? (d.lastQ || 'Última pregunta alcanzada') : (d.nextQ || 'Siguiente pregunta')}
        >
          {questionIndex >= totalQuestions ? (d.lastQ || 'Última pregunta ✓') : `${d.nextQ || 'Siguiente'} ➔`}
        </button>

        <div
          className="meter col"
          style={{ maxWidth: '240px' }}
          role="progressbar"
          aria-valuenow={questionIndex}
          aria-valuemin={1}
          aria-valuemax={totalQuestions}
          aria-label={d.questionOf ? d.questionOf.replace('{i}', String(questionIndex)).replace('{n}', String(totalQuestions)) : `Pregunta ${questionIndex} de ${totalQuestions}`}
        >
          <i
            style={{
              width: `${(questionIndex / totalQuestions) * 100}%`,
              background: 'var(--accent)'
            }}
          />
        </div>

        <span style={{ fontSize: '12.5px', color: 'var(--muted)', fontWeight: 500 }}>
          {d.questionOf
            ? d.questionOf.replace('{i}', String(questionIndex)).replace('{n}', String(totalQuestions))
            : `Pregunta ${questionIndex} de ${totalQuestions}`}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            type="button"
            className="btn ghost live-session-cancel-btn"
            onClick={() => handleOpenCancelModal('manual')}
            disabled={isUploading}
            aria-label={d.cancelTitle || 'Cancelar ejercitación'}
            title={d.cancelTitle || 'Cancelar ejercitación y descartar grabación'}
          >
            {d.cancel || '✕ Cancelar'}
          </button>

          <button
            type="button"
            className="btn pri live-session-finish-btn"
            onClick={handleFinishSession}
            disabled={isUploading}
            aria-label={d.finish || 'Finalizar entrevista'}
          >
            {isUploading ? (d.uploading || 'Subiendo grabación...') : `${d.finish} · Enviar a Evaluación 🚀`}
          </button>
        </div>
      </div>

      {/* Modal de confirmación para cancelar ejercitación */}
      <CancelExerciseModal
        isOpen={showCancelModal}
        reason={cancelModalReason}
        continueText={d.continueBtn}
        cancelText={d.confirmCancelBtn}
        onContinue={handleContinueFromModal}
        onConfirmCancel={handleConfirmCancel}
      />
    </div>
  );
};
