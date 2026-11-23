'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { VoceroScreen } from './HomePracticeView';
import { sessionService, type QuestionMark } from '../../services/sessionService';
import { interviewLiveService } from '../../services/interviewLiveService';
import type { SessionSetup } from '../../services/sessionFlowService';
import type { TurnInterval } from '../../types/api';
import { InterviewerAvatar } from './InterviewerAvatar';
import { CancelExerciseModal, type CancelModalReason } from './CancelExerciseModal';

type TurnPhase = 'interviewer_speaking' | 'recording_answer' | 'evaluating_followup' | 'completed';

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

  const isIndeterminate = uploadProgress === null;

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
          className={`upload-overlay-bar-fill ${isIndeterminate ? 'indeterminate' : ''}`}
          style={{
            width: !isIndeterminate ? `${Math.max(0, Math.min(100, uploadProgress))}%` : undefined
          }}
        />
      </div>
      {!isIndeterminate && (
        <span style={{ fontSize: '11.5px', color: '#6ee7b7', marginTop: '8px', fontWeight: 600 }}>
          {Math.round(uploadProgress)}%
        </span>
      )}
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

  const [generatedSessionId] = useState(() => typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`);
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
  const [turnIndex, setTurnIndex] = useState(1);
  const [turnPhase, setTurnPhase] = useState<TurnPhase>('interviewer_speaking');
  const [isAdvanceLocked, setIsAdvanceLocked] = useState(true);
  const [activeFollowUp, setActiveFollowUp] = useState<{ text: string; parentTurnId: string } | null>(null);
  const [isUserTurn, setIsUserTurn] = useState(false);
  const totalQuestions = questions.length;
  const sessionDifficulty = setup?.difficulty || setup?.followUpPolicy?.difficulty || 'intermediate';

  // Estados de captura de video maestro y audio por turno (doble MediaRecorder)
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const turnRecorderRef = useRef<MediaRecorder | null>(null);
  const turnChunksRef = useRef<Blob[]>([]);
  const turnStartOffsetMsRef = useRef<number>(0);
  const advanceUnlockTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFinishingTurnRef = useRef(false);
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

  const currentQuestion = activeFollowUp
    ? activeFollowUp.text
    : (questions[questionIndex - 1] || questions[0] || d.qEx);
  const activeTurnKey = `${turnIndex}-${activeFollowUp ? 'fu' : 'base'}-${questionIndex}`;

  // Limpieza al desmontar
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (navTimerRef.current) clearTimeout(navTimerRef.current);
      if (safetyTimerRef.current) clearTimeout(safetyTimerRef.current);
      if (advanceUnlockTimerRef.current) clearTimeout(advanceUnlockTimerRef.current);
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
        } catch { }

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
          videoBitsPerSecond: 1200000, // 1.2 Mbps optimizado para entrevistas de hasta 15 min
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
      if (turnRecorderRef.current && turnRecorderRef.current.state !== 'inactive') {
        try {
          turnRecorderRef.current.stop();
        } catch { }
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch { }
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

  // Sincronizar estado de AMBOS MediaRecorder (video maestro + audio del turno) con pausa/reanudación
  useEffect(() => {
    const syncRecorder = (rec: MediaRecorder | null, label: string) => {
      if (!rec) return;
      if (isPaused && rec.state === 'recording') {
        try {
          rec.pause();
        } catch (e) {
          console.warn(`Advertencia al pausar ${label}:`, e);
        }
      } else if (!isPaused && rec.state === 'paused') {
        try {
          rec.resume();
        } catch (e) {
          console.warn(`Advertencia al reanudar ${label}:`, e);
        }
      }
    };
    syncRecorder(mediaRecorderRef.current, 'sessionRecorder');
    syncRecorder(turnRecorderRef.current, 'turnAudioRecorder');
  }, [isPaused]);

  // Grabador dedicado de audio por turno (inicia inmediatamente en utterance.onend)
  const startTurnAudioRecorder = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    const audioTracks = stream.getAudioTracks();
    if (!audioTracks || audioTracks.length === 0) return;

    if (turnRecorderRef.current && turnRecorderRef.current.state !== 'inactive') {
      try {
        turnRecorderRef.current.ondataavailable = null;
        turnRecorderRef.current.onstop = null;
        turnRecorderRef.current.stop();
      } catch {}
    }

    const audioOnlyStream = new MediaStream(audioTracks);
    let audioMime = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(audioMime)) {
      if (MediaRecorder.isTypeSupported('audio/webm')) {
        audioMime = 'audio/webm';
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        audioMime = 'audio/mp4';
      } else {
        audioMime = '';
      }
    }

    try {
      const turnRec = new MediaRecorder(audioOnlyStream, {
        ...(audioMime ? { mimeType: audioMime } : {}),
        audioBitsPerSecond: 64000
      });
      turnChunksRef.current = [];
      turnRec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          turnChunksRef.current.push(e.data);
        }
      };
      turnStartOffsetMsRef.current = Math.round(getElapsedMs());
      turnRec.start();
      turnRecorderRef.current = turnRec;
    } catch (err) {
      console.warn('[LiveSessionView] No se pudo iniciar turnAudioRecorder:', err);
      turnRecorderRef.current = null;
    }
  }, [getElapsedMs]);

  const stopTurnAudioRecorder = useCallback(async (): Promise<Blob | null> => {
    const turnRec = turnRecorderRef.current;
    if (!turnRec || turnRec.state === 'inactive') {
      turnRecorderRef.current = null;
      return null;
    }

    await new Promise<void>((resolve) => {
      const safety = setTimeout(() => resolve(), 2000);
      turnRec.onstop = () => {
        clearTimeout(safety);
        resolve();
      };
      try {
        if (typeof turnRec.requestData === 'function' && turnRec.state === 'recording') {
          turnRec.requestData();
        }
      } catch {}
      try {
        turnRec.stop();
      } catch {
        clearTimeout(safety);
        resolve();
      }
    });

    turnRecorderRef.current = null;
    if (turnChunksRef.current.length === 0) return null;
    const type = turnRec.mimeType || 'audio/webm';
    const blob = new Blob(turnChunksRef.current, { type });
    turnChunksRef.current = [];
    return blob;
  }, []);

  // Al terminar la locución del avatar (o en modo Mute/watchdog):
  // 1) Inicia turnAudioRecorder INMEDIATAMENTE (sin retraso para no cortar las primeras palabras)
  // 2) Bloquea solo el botón "Terminé de responder" por ~1 segundo para evitar doble clic accidental
  const handleAvatarSpeechEnd = useCallback(() => {
    if (!isMountedRef.current || isUploading) return;
    setTurnPhase('recording_answer');
    setIsUserTurn(true);
    setIsAdvanceLocked(true);
    startTurnAudioRecorder();

    if (advanceUnlockTimerRef.current) {
      clearTimeout(advanceUnlockTimerRef.current);
    }
    advanceUnlockTimerRef.current = setTimeout(() => {
      if (isMountedRef.current) {
        setIsAdvanceLocked(false);
      }
    }, 1000);
  }, [isUploading, startTurnAudioRecorder]);

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

    // 1. Detener ambos MediaRecorder y anular callbacks
    if (turnRecorderRef.current) {
      try {
        turnRecorderRef.current.ondataavailable = null;
        turnRecorderRef.current.onstop = null;
        if (turnRecorderRef.current.state !== 'inactive') {
          turnRecorderRef.current.stop();
        }
      } catch {}
      turnRecorderRef.current = null;
      turnChunksRef.current = [];
    }
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

  // Finalizar sesión y detener grabadora (despachando antes el turno activo si corresponde)
  const handleFinishSession = async (turnAlreadySubmitted = false) => {
    setUploadError(null);
    setIsUploading(true);
    setUploadProgress(null);
    setUploadStatus(d.finalizingRecording || 'Finalizando grabación…');

    if (!turnAlreadySubmitted && turnRecorderRef.current && turnRecorderRef.current.state !== 'inactive') {
      try {
        const partialEndMs = Math.round(getElapsedMs());
        const partialBlob = await stopTurnAudioRecorder();
        if (partialBlob && partialBlob.size > 0) {
          await interviewLiveService.submitTurn({
            sessionId: activeSessionId,
            audioBlob: partialBlob,
            baseSequenceNo: questionIndex,
            turnIndex,
            turnKind: activeFollowUp ? 'follow_up' : 'base',
            questionText: currentQuestion,
            parentTurnId: activeFollowUp?.parentTurnId || null,
            startOffsetMs: turnStartOffsetMsRef.current,
            endOffsetMs: partialEndMs,
            timeoutMs: 6000
          });
        }
      } catch (e) {
        console.warn('[LiveSessionView] Aviso enviando último turno parcial al finalizar:', e);
      }
    }

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

  // Completar turno actual: detiene turnAudioRecorder, consulta contrapregunta a Gemini y avanza
  const handleCompleteTurn = async () => {
    if (
      isFinishingTurnRef.current ||
      turnPhase !== 'recording_answer' ||
      isAdvanceLocked ||
      isPaused ||
      isUploading
    ) {
      return;
    }

    isFinishingTurnRef.current = true;
    setTurnPhase('evaluating_followup');
    setIsUserTurn(false);
    setIsAdvanceLocked(true);

    try {
      const endOffsetMs = Math.round(getElapsedMs());
      const marks = marksRef.current;
      const lastMark = marks[marks.length - 1];
      if (lastMark && lastMark.endMs === null) {
        lastMark.endMs = endOffsetMs;
      }

      const audioBlob = await stopTurnAudioRecorder();
      let hasFollowUp = false;
      let followUpText: string | null = null;
      let turnId = '';

      if (audioBlob && audioBlob.size > 0) {
        const res = await interviewLiveService.submitTurn({
          sessionId: activeSessionId,
          audioBlob,
          baseSequenceNo: questionIndex,
          turnIndex,
          turnKind: activeFollowUp ? 'follow_up' : 'base',
          questionText: currentQuestion,
          parentTurnId: activeFollowUp?.parentTurnId || null,
          startOffsetMs: turnStartOffsetMsRef.current,
          endOffsetMs,
          timeoutMs: 15000
        });
        hasFollowUp = Boolean(res.hasFollowUp && res.followUpQuestion);
        followUpText = res.followUpQuestion;
        turnId = res.turnId;
      }

      if (!isMountedRef.current) return;

      if (hasFollowUp && followUpText) {
        setActiveFollowUp({ text: followUpText, parentTurnId: turnId });
        setTurnIndex((prev) => prev + 1);
        setTurnPhase('interviewer_speaking');
        marks.push({ questionIndex, startMs: getElapsedMs(), endMs: null });
      } else if (questionIndex < totalQuestions) {
        const nextBaseIdx = questionIndex + 1;
        setActiveFollowUp(null);
        setQuestionIndex(nextBaseIdx);
        setTurnIndex((prev) => prev + 1);
        setTurnPhase('interviewer_speaking');
        marks.push({ questionIndex: nextBaseIdx, startMs: getElapsedMs(), endMs: null });
      } else {
        setActiveFollowUp(null);
        setTurnPhase('completed');
        await handleFinishSession(true);
      }
    } finally {
      isFinishingTurnRef.current = false;
    }
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
            turnKey={activeTurnKey}
            isFollowUp={activeFollowUp !== null}
            allowRepeat={turnPhase === 'interviewer_speaking'}
            isPaused={isPaused || turnPhase === 'evaluating_followup' || turnPhase === 'completed'}
            onSpeechStart={() => setTurnPhase('interviewer_speaking')}
            onSpeechEnd={handleAvatarSpeechEnd}
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
          borderLeft: activeFollowUp ? '4px solid #f59e0b' : '4px solid var(--accent2)',
          background: 'var(--panel)',
          position: 'relative'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="label" style={{ margin: 0 }}>
              {activeFollowUp ? '⚡ Contrapregunta en vivo' : d.qL}
            </div>
            <span
              style={{
                fontSize: '10.5px',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '2px 7px',
                borderRadius: '999px',
                background: 'var(--soft)',
                color: 'var(--muted)',
                border: '1px solid var(--line)'
              }}
            >
              {sessionDifficulty === 'basic'
                ? 'Nivel Fácil'
                : sessionDifficulty === 'hard'
                ? 'Nivel Difícil'
                : 'Nivel Intermedio'}
            </span>
          </div>

          {turnPhase === 'evaluating_followup' ? (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#818cf8',
                background: 'rgba(99, 102, 241, 0.14)',
                border: '1px solid rgba(99, 102, 241, 0.35)',
                padding: '2px 10px',
                borderRadius: '999px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              ⏳ Analizando respuesta...
            </span>
          ) : turnPhase === 'recording_answer' && isUserTurn && !isPaused ? (
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
              🎤 {d.yourTurn || 'Tu turno · Grabando'}
            </span>
          ) : (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: '#38bdf8',
                background: 'rgba(56, 189, 248, 0.1)',
                border: '1px solid rgba(56, 189, 248, 0.25)',
                padding: '2px 8px',
                borderRadius: '999px'
              }}
            >
              🗣️ Escucha al entrevistador...
            </span>
          )}
        </div>
        <div
          style={{
            fontSize: '17px',
            lineHeight: 1.5,
            color: 'var(--ink)',
            fontWeight: 500,
            marginTop: '6px'
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
          disabled={turnPhase === 'evaluating_followup' || isUploading}
          aria-label={isPaused ? d.resume : d.pause}
        >
          {isPaused ? d.resume : d.pause}
        </button>

        <button
          type="button"
          className="btn pri"
          onClick={handleCompleteTurn}
          disabled={
            turnPhase !== 'recording_answer' ||
            isAdvanceLocked ||
            isPaused ||
            isUploading
          }
          aria-label="Terminé de responder"
          title={
            turnPhase === 'interviewer_speaking'
              ? 'Espera a que el entrevistador termine la pregunta'
              : turnPhase === 'evaluating_followup'
              ? 'Evaluando respuesta...'
              : 'Enviar respuesta de este turno y continuar'
          }
        >
          {turnPhase === 'evaluating_followup'
            ? '⏳ Evaluando respuesta...'
            : questionIndex >= totalQuestions && activeFollowUp !== null
            ? 'Terminé de responder · Finalizar 🚀'
            : 'Terminé de responder ➔'}
        </button>

        <div
          className="meter col"
          style={{ maxWidth: '220px' }}
          role="progressbar"
          aria-valuenow={questionIndex}
          aria-valuemin={1}
          aria-valuemax={totalQuestions}
          aria-label={d.questionOf ? d.questionOf.replace('{i}', String(questionIndex)).replace('{n}', String(totalQuestions)) : `Pregunta ${questionIndex} de ${totalQuestions}`}
        >
          <i
            style={{
              width: `${(questionIndex / totalQuestions) * 100}%`,
              background: activeFollowUp ? '#f59e0b' : 'var(--accent)'
            }}
          />
        </div>

        <span style={{ fontSize: '12.5px', color: 'var(--muted)', fontWeight: 500 }}>
          {d.questionOf
            ? d.questionOf.replace('{i}', String(questionIndex)).replace('{n}', String(totalQuestions))
            : `Pregunta ${questionIndex} de ${totalQuestions}`}
          {activeFollowUp ? ' · Contrapregunta' : ''}
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
            className="btn ghost live-session-finish-btn"
            onClick={() => handleFinishSession(false)}
            disabled={isUploading || turnPhase === 'evaluating_followup'}
            aria-label={d.finish || 'Finalizar anticipadamente'}
            title="Finalizar la entrevista ahora y enviar a evaluación"
          >
            {isUploading ? (d.uploading || 'Subiendo grabación...') : 'Finalizar anticipadamente'}
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
