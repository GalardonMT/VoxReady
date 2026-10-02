'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { VoceroScreen } from './HomePracticeView';

interface TechConsentViewProps {
  onNavigate: (screen: VoceroScreen) => void;
}

export const TechConsentView: React.FC<TechConsentViewProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.u3;

  const [chk1, setChk1] = useState(false);
  const [chk2, setChk2] = useState(false);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const [streamActive, setStreamActive] = useState(false);

  // Lista y selección de dispositivos de entrada
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string>('');
  const [selectedAudioId, setSelectedAudioId] = useState<string>('');

  // Estados de micrófono en tiempo real
  const [audioLevel, setAudioLevel] = useState(0); // 0 a 100
  const [micPassed, setMicPassed] = useState(false);
  const MIC_THRESHOLD = 20; // Umbral mínimo de audio requerido (20%) para asegurar que se habló claro

  // Estados de iluminación en tiempo real
  const [lightLevel, setLightLevel] = useState(0); // 0 a 100
  const [lightPassed, setLightPassed] = useState(false);
  const LIGHT_MIN_THRESHOLD = 30; // Mínimo 30% para no estar demasiado oscuro
  const LIGHT_MAX_THRESHOLD = 90; // Máximo 90% para no estar sobreexpuesto

  // Cargar dispositivos guardados de localStorage si existen
  React.useEffect(() => {
    try {
      const savedVideo = localStorage.getItem('voxready_selected_camera');
      const savedAudio = localStorage.getItem('voxready_selected_mic');
      if (savedVideo) setSelectedVideoId(savedVideo);
      if (savedAudio) setSelectedAudioId(savedAudio);
    } catch {}
  }, []);

  // Función para listar cámaras y micrófonos con etiquetas
  const enumerateUserDevices = async () => {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const vDevs = devices.filter((d) => d.kind === 'videoinput');
      const aDevs = devices.filter((d) => d.kind === 'audioinput');
      setVideoDevices(vDevs);
      setAudioDevices(aDevs);

      // Si no hay seleccionado o el seleccionado ya no existe, tomar el primero
      setSelectedVideoId((prev) => {
        if (prev && vDevs.some((d) => d.deviceId === prev)) return prev;
        return vDevs[0]?.deviceId || '';
      });
      setSelectedAudioId((prev) => {
        if (prev && aDevs.some((d) => d.deviceId === prev)) return prev;
        return aDevs[0]?.deviceId || '';
      });
    } catch (e) {
      console.warn('Error listando dispositivos:', e);
    }
  };

  // Re-iniciar stream cada vez que cambie selectedVideoId o selectedAudioId
  React.useEffect(() => {
    let stream: MediaStream | null = null;
    let audioContext: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    let animationFrameId: number;
    let lightIntervalId: NodeJS.Timeout;

    async function setupDevices() {
      try {
        const videoConstraints: MediaTrackConstraints = {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          ...(selectedVideoId ? { deviceId: { exact: selectedVideoId } } : {})
        };

        const audioConstraints: MediaTrackConstraints = {
          echoCancellation: true,
          noiseSuppression: false,
          autoGainControl: false,
          ...(selectedAudioId ? { deviceId: { exact: selectedAudioId } } : {})
        };

        stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: audioConstraints
        });

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setStreamActive(true);

        // Guardar preferencias seleccionadas
        if (selectedVideoId) {
          try { localStorage.setItem('voxready_selected_camera', selectedVideoId); } catch {}
        }
        if (selectedAudioId) {
          try { localStorage.setItem('voxready_selected_mic', selectedAudioId); } catch {}
        }

        // Una vez concedidos permisos, listar dispositivos para obtener etiquetas reales
        await enumerateUserDevices();

        // --- 1. CONFIGURACIÓN DEL MICRÓFONO CON WEB AUDIO API ---
        const audioTracks = stream.getAudioTracks();
        if (audioTracks.length > 0) {
          const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
          audioContext = new AudioContextClass();
          
          if (audioContext.state === 'suspended') {
            await audioContext.resume();
          }

          const source = audioContext.createMediaStreamSource(stream);
          analyser = audioContext.createAnalyser();
          analyser.fftSize = 512;
          analyser.smoothingTimeConstant = 0.3; // Más responsivo al habla inmediata
          source.connect(analyser);

          const timeData = new Uint8Array(analyser.fftSize);
          let framesOverThreshold = 0;

          const checkAudio = () => {
            if (!analyser) return;
            analyser.getByteTimeDomainData(timeData);

            // Calcular desviación respecto al silencio (amplitud real pico a pico / RMS)
            let sumSquares = 0;
            for (let i = 0; i < timeData.length; i++) {
              const deviation = (timeData[i] - 128) / 128; // normalizado -1 a 1
              sumSquares += deviation * deviation;
            }
            const rms = Math.sqrt(sumSquares / timeData.length);
            
            // Factor de ganancia visual para escala de 0 a 100 realista
            const currentLevel = Math.min(100, Math.round(rms * 280));
            setAudioLevel(currentLevel);

            // Requiere al menos 6 frames consecutivos por encima del umbral (habla real)
            if (currentLevel >= MIC_THRESHOLD) {
              framesOverThreshold++;
              if (framesOverThreshold >= 6) {
                setMicPassed(true);
              }
            } else {
              framesOverThreshold = Math.max(0, framesOverThreshold - 1);
            }

            animationFrameId = requestAnimationFrame(checkAudio);
          };
          checkAudio();
        }

        // --- 2. CONFIGURACIÓN DE ILUMINACIÓN MEDIANTE CANVAS ---
        const checkLighting = () => {
          const video = videoRef.current;
          const canvas = canvasRef.current;
          if (!video || !canvas || video.readyState < 2) return;

          const ctx = canvas.getContext('2d', { willReadFrequently: true });
          if (!ctx) return;

          const w = 48;
          const h = 36;
          canvas.width = w;
          canvas.height = h;

          ctx.drawImage(video, 0, 0, w, h);
          const imageData = ctx.getImageData(0, 0, w, h);
          const data = imageData.data;

          let totalBrightness = 0;
          const totalPixels = data.length / 4;

          // Fórmula de luminancia perceptual estándar (Rec. 601)
          for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            totalBrightness += 0.299 * r + 0.587 * g + 0.114 * b;
          }

          const avgBrightness = Math.round((totalBrightness / totalPixels / 255) * 100);
          setLightLevel(avgBrightness);

          if (avgBrightness >= LIGHT_MIN_THRESHOLD && avgBrightness <= LIGHT_MAX_THRESHOLD) {
            setLightPassed(true);
          } else {
            setLightPassed(false);
          }
        };

        // Medir iluminación periódicamente (cada 400ms para ahorrar CPU)
        lightIntervalId = setInterval(checkLighting, 400);

      } catch (e) {
        console.warn('Error accediendo a dispositivos en TechConsentView:', e);
      }
    }

    setupDevices();

    // Escuchar cuando se conecta o desconecta un dispositivo USB
    const handleDeviceChange = () => {
      enumerateUserDevices();
    };
    navigator.mediaDevices?.addEventListener('devicechange', handleDeviceChange);

    return () => {
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      if (lightIntervalId) clearInterval(lightIntervalId);
      navigator.mediaDevices?.removeEventListener('devicechange', handleDeviceChange);
      if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [selectedVideoId, selectedAudioId]);

  const isTechnicalReady = streamActive && micPassed && lightPassed;
  const isEnabled = chk1 && chk2 && isTechnicalReady;

  return (
    <div className="canvas-content">
      {/* Canvas invisible para el cálculo de luminosidad */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      <div className="row">
        {/* Left Column: Tech validation */}
        <div className="card col">
          <div className="label">{d.camL}</div>
          <div className="self" style={{ minHeight: '220px', position: 'relative', overflow: 'hidden', borderRadius: '8px', background: '#000' }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                minHeight: '220px',
                objectFit: 'cover',
                transform: 'scaleX(-1)',
                display: streamActive ? 'block' : 'none'
              }}
            />
            {!streamActive && (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <div style={{ fontSize: '38px', marginBottom: '8px' }}>👤</div>
                <div style={{ fontSize: '13px', color: '#cdd4da' }}>{d.camL || 'Iniciando cámara...'}</div>
              </div>
            )}
            
            {/* Badge de estado de cámara: compacto, discreto y sin fondo invasivo */}
            <div
              style={{
                position: 'absolute',
                top: '10px',
                right: '10px',
                background: 'rgba(15, 23, 42, 0.75)',
                backdropFilter: 'blur(6px)',
                color: '#fff',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                border: '1px solid rgba(255, 255, 255, 0.1)'
              }}
            >
              <i
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: streamActive ? '#22c55e' : '#ef4444'
                }}
              />
              <span>{streamActive ? (d.camOk || 'Cámara activa') : 'Conectando'}</span>
            </div>
          </div>

          <div style={{ marginTop: '16px' }}>
            {/* Medidor de Micrófono con umbral y feedback interactivo */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12px',
                marginBottom: '5px'
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 500, flexWrap: 'wrap' }}>
                🎤 Micrófono
                <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400 }}>
                  ({micPassed ? 'superó el umbral: correcto' : 'si supera el umbral está correcto'})
                </span>
              </span>
              <span
                style={{
                  color: micPassed ? '#22c55e' : '#eab308',
                  fontWeight: 600,
                  fontSize: '11.5px'
                }}
              >
                {micPassed ? `✓ Audio correcto (${audioLevel}%)` : `Requiere hablar (mín. ${MIC_THRESHOLD}%)`}
              </span>
            </div>
            <div
              className="meter"
              style={{
                position: 'relative',
                background: 'rgba(0,0,0,0.1)',
                height: '8px',
                borderRadius: '4px',
                overflow: 'hidden'
              }}
            >
              {/* Marca del umbral */}
              <div
                style={{
                  position: 'absolute',
                  left: `${MIC_THRESHOLD}%`,
                  top: 0,
                  bottom: 0,
                  width: '2px',
                  background: 'rgba(255, 255, 255, 0.8)',
                  boxShadow: '0 0 4px rgba(0,0,0,0.5)',
                  zIndex: 2
                }}
                title={`Umbral requerido: ${MIC_THRESHOLD}%`}
              />
              <i
                style={{
                  width: `${audioLevel}%`,
                  background: audioLevel >= MIC_THRESHOLD ? '#22c55e' : '#eab308',
                  transition: 'width 0.08s ease-out'
                }}
              />
            </div>

            {/* Medidor de Iluminación con umbral requerido */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12px',
                margin: '14px 0 5px'
              }}
            >
              <span style={{ fontWeight: 500 }}>💡 Iluminación de sala</span>
              <span
                style={{
                  color: lightPassed
                    ? '#22c55e'
                    : lightLevel < LIGHT_MIN_THRESHOLD
                    ? '#eab308'
                    : '#ef4444',
                  fontWeight: 600,
                  fontSize: '11.5px'
                }}
              >
                {lightPassed
                  ? `✓ Óptima (${lightLevel}%)`
                  : lightLevel < LIGHT_MIN_THRESHOLD
                  ? `Baja (${lightLevel}% / mín. ${LIGHT_MIN_THRESHOLD}%)`
                  : `Muy brillante (${lightLevel}%)`}
              </span>
            </div>
            <div
              className="meter"
              style={{
                position: 'relative',
                background: 'rgba(0,0,0,0.1)',
                height: '8px',
                borderRadius: '4px',
                overflow: 'hidden'
              }}
            >
              {/* Marca de umbral mínimo */}
              <div
                style={{
                  position: 'absolute',
                  left: `${LIGHT_MIN_THRESHOLD}%`,
                  top: 0,
                  bottom: 0,
                  width: '2px',
                  background: 'rgba(255, 255, 255, 0.7)',
                  zIndex: 2
                }}
                title={`Mínimo requerido: ${LIGHT_MIN_THRESHOLD}%`}
              />
              <i
                style={{
                  width: `${lightLevel}%`,
                  background: lightPassed
                    ? '#22c55e'
                    : lightLevel < LIGHT_MIN_THRESHOLD
                    ? '#eab308'
                    : '#ef4444',
                  transition: 'width 0.3s ease'
                }}
              />
            </div>

            {/* Selectores de Dispositivos (Cámara y Micrófono) */}
            <div
              style={{
                marginTop: '16px',
                paddingTop: '14px',
                borderTop: '1px solid var(--line)',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px'
              }}
            >
              <div>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    color: 'var(--muted)',
                    textTransform: 'uppercase',
                    marginBottom: '4px',
                    letterSpacing: '0.04em'
                  }}
                >
                  📹 Cámara
                </label>
                <select
                  value={selectedVideoId}
                  onChange={(e) => setSelectedVideoId(e.target.value)}
                  className="field"
                  style={{
                    width: '100%',
                    fontSize: '12px',
                    background: 'var(--panel)',
                    color: 'var(--ink)',
                    cursor: 'pointer',
                    borderRadius: '6px'
                  }}
                >
                  {videoDevices.length === 0 ? (
                    <option value="">Cámara por defecto</option>
                  ) : (
                    videoDevices.map((dev, idx) => (
                      <option key={dev.deviceId || idx} value={dev.deviceId}>
                        {dev.label || `Cámara ${idx + 1}`}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    color: 'var(--muted)',
                    textTransform: 'uppercase',
                    marginBottom: '4px',
                    letterSpacing: '0.04em'
                  }}
                >
                  🎙️ Micrófono
                </label>
                <select
                  value={selectedAudioId}
                  onChange={(e) => {
                    setSelectedAudioId(e.target.value);
                    setMicPassed(false); // Pedir hablar de nuevo al cambiar de micrófono
                  }}
                  className="field"
                  style={{
                    width: '100%',
                    fontSize: '12px',
                    background: 'var(--panel)',
                    color: 'var(--ink)',
                    cursor: 'pointer',
                    borderRadius: '6px'
                  }}
                >
                  {audioDevices.length === 0 ? (
                    <option value="">Micrófono por defecto</option>
                  ) : (
                    audioDevices.map((dev, idx) => (
                      <option key={dev.deviceId || idx} value={dev.deviceId}>
                        {dev.label || `Micrófono ${idx + 1}`}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>

            {!isTechnicalReady && (
              <div
                style={{
                  marginTop: '12px',
                  fontSize: '11.5px',
                  color: '#eab308',
                  background: 'rgba(234, 179, 8, 0.08)',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: '1px solid rgba(234, 179, 8, 0.2)',
                  lineHeight: 1.45
                }}
              >
                {!streamActive
                  ? '• Activa los permisos de tu cámara web.'
                  : !micPassed
                  ? '• Pronuncia unas palabras en el micrófono seleccionado para validar el umbral.'
                  : '• Ajusta la iluminación de tu entorno (mínimo 30%).'}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Consent & Legal */}
        <div className="card col">
          <div className="label">{d.consentL}</div>
          <div
            className="area"
            style={{
              minHeight: '120px',
              fontSize: '12.5px',
              lineHeight: 1.5,
              color: 'var(--ink)'
            }}
          >
            {d.legal}
          </div>

          <div style={{ marginTop: '14px' }}>
            <label
              style={{
                display: 'flex',
                gap: '10px',
                alignItems: 'flex-start',
                fontSize: '12.5px',
                cursor: 'pointer',
                marginBottom: '10px'
              }}
            >
              <input
                type="checkbox"
                checked={chk1}
                onChange={(e) => setChk1(e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  accentColor: 'var(--accent2)',
                  marginTop: '2px',
                  cursor: 'pointer'
                }}
              />
              <span>{d.chk1}</span>
            </label>

            <label
              style={{
                display: 'flex',
                gap: '10px',
                alignItems: 'flex-start',
                fontSize: '12.5px',
                cursor: 'pointer'
              }}
            >
              <input
                type="checkbox"
                checked={chk2}
                onChange={(e) => setChk2(e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  accentColor: 'var(--accent2)',
                  marginTop: '2px',
                  cursor: 'pointer'
                }}
              />
              <span>{d.chk2}</span>
            </label>
          </div>

          <div
            style={{
              marginTop: '20px',
              display: 'flex',
              gap: '10px',
              alignItems: 'center'
            }}
          >
            <button
              type="button"
              className={`btn pri ${!isEnabled ? 'disabled' : ''}`}
              onClick={() => {
                if (isEnabled) onNavigate('u4');
              }}
            >
              {d.beginBtn} →
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => onNavigate('u2')}
            >
              {d.cancel}
            </button>
          </div>

          <div className="legend" style={{ marginTop: '8px' }}>
            {d.sesLang}
          </div>
        </div>
      </div>
    </div>
  );
};
