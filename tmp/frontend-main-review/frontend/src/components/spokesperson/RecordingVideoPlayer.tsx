'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

interface RecordingVideoPlayerProps {
  src: string;
  expectedDuration?: number;
  autoPlay?: boolean;
}

export const formatTime = (seconds: number): string => {
  if (!isFinite(seconds) || isNaN(seconds) || seconds < 0) return '00:00';
  const totalSecs = Math.floor(seconds);
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

export const RecordingVideoPlayer: React.FC<RecordingVideoPlayerProps> = ({
  src,
  expectedDuration = 0,
  autoPlay = false
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const progressBarRef = useRef<HTMLDivElement | null>(null);

  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(expectedDuration || 0);
  const [bufferedEnd, setBufferedEnd] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isBuffering, setIsBuffering] = useState<boolean>(false);
  const [volume, setVolume] = useState<number>(1);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showControls, setShowControls] = useState<boolean>(true);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [hoverPosition, setHoverPosition] = useState<number>(0);

  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Determinar la duración efectiva más confiable
  const effectiveDuration =
    duration && isFinite(duration) && duration > 0
      ? duration
      : expectedDuration && isFinite(expectedDuration) && expectedDuration > 0
        ? expectedDuration
        : 0;

  // Actualizar duración si expectedDuration cambia y no tenemos una duración finita detectada
  useEffect(() => {
    if (expectedDuration && expectedDuration > 0 && (!duration || !isFinite(duration))) {
      setDuration(expectedDuration);
    }
  }, [expectedDuration, duration]);

  // Resolución del bug de Chromium con archivos WebM de MediaRecorder (duration = Infinity)
  const resolveChromiumDuration = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    if (isFinite(video.duration) && video.duration > 0) {
      setDuration(video.duration);
    } else {
      // Forzar al navegador a leer el último cluster del WebM mediante seek temporal
      const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked);
        if (isFinite(video.duration) && video.duration > 0) {
          setDuration(video.duration);
        } else if (expectedDuration && expectedDuration > 0) {
          setDuration(expectedDuration);
        }
        video.currentTime = 0;
      };

      video.addEventListener('seeked', onSeeked);
      // Usar número grande para alcanzar el final del archivo WebM
      video.currentTime = 1e10;
    }
  }, [expectedDuration]);

  // Manejo de eventos del elemento <video>
  const handleLoadedMetadata = () => {
    resolveChromiumDuration();
    if (autoPlay && videoRef.current) {
      videoRef.current.play().catch(() => {
        // Autoplay con audio puede requerir interacción de usuario
      });
    }
  };

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    if (!isDragging) {
      setCurrentTime(video.currentTime);
    }

    // Calcular buffer progresivo
    if (video.buffered && video.buffered.length > 0) {
      try {
        const end = video.buffered.end(video.buffered.length - 1);
        setBufferedEnd(end);
      } catch {
        // ignore
      }
    }

    // Si el navegador descubrió la duración durante la reproducción, sincronizarla
    if (isFinite(video.duration) && video.duration > 0 && Math.abs(duration - video.duration) > 0.5) {
      setDuration(video.duration);
    }
  };

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused || video.ended) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, []);

  const skipSeconds = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    const max = effectiveDuration > 0 ? effectiveDuration : video.duration || 99999;
    const nextTime = Math.max(0, Math.min(max, video.currentTime + seconds));
    video.currentTime = nextTime;
    setCurrentTime(nextTime);
  };

  // Manejo de timeline y scrubber
  const seekToPosition = useCallback(
    (clientX: number) => {
      const progressBar = progressBarRef.current;
      const video = videoRef.current;
      if (!progressBar || !video || effectiveDuration <= 0) return;

      const rect = progressBar.getBoundingClientRect();
      const clickX = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const percentage = clickX / rect.width;
      const newTime = percentage * effectiveDuration;

      video.currentTime = newTime;
      setCurrentTime(newTime);
    },
    [effectiveDuration]
  );

  const handleProgressBarMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    setIsDragging(true);
    seekToPosition(e.clientX);
  };

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (isDragging) {
        seekToPosition(e.clientX);
      }
    },
    [isDragging, seekToPosition]
  );

  const handleMouseUp = useCallback(() => {
    if (isDragging) {
      setIsDragging(false);
    }
  }, [isDragging]);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Tooltip con preview de tiempo al pasar el mouse por la barra
  const handleProgressHover = (e: React.MouseEvent<HTMLDivElement>) => {
    if (effectiveDuration <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const hoverX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const pct = hoverX / rect.width;
    setHoverTime(pct * effectiveDuration);
    setHoverPosition(hoverX);
  };

  // Volumen
  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      videoRef.current.muted = val === 0;
      setIsMuted(val === 0);
    }
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    if (isMuted) {
      video.muted = false;
      video.volume = volume || 1;
      setIsMuted(false);
    } else {
      video.muted = true;
      setIsMuted(true);
    }
  };

  // Velocidad de reproducción
  const speedOptions = [0.75, 1, 1.25, 1.5, 2];
  const cyclePlaybackRate = () => {
    const video = videoRef.current;
    if (!video) return;
    const currentIndex = speedOptions.indexOf(playbackRate);
    const nextRate = speedOptions[(currentIndex + 1) % speedOptions.length];
    video.playbackRate = nextRate;
    setPlaybackRate(nextRate);
  };

  // Pantalla completa
  const toggleFullscreen = () => {
    const container = containerRef.current;
    if (!container) return;

    if (!document.fullscreenElement) {
      container.requestFullscreen?.().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.().catch(() => {});
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // Ocultar controles automáticamente cuando está reproduciendo
  const handleUserActivity = () => {
    setShowControls(true);
    if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    if (isPlaying) {
      hideTimeoutRef.current = setTimeout(() => {
        setShowControls(false);
      }, 2500);
    }
  };

  // Atajos de teclado
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignorar si el usuario está escribiendo en un input
      if (['input', 'textarea', 'select'].includes((e.target as HTMLElement)?.tagName?.toLowerCase())) {
        return;
      }

      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        skipSeconds(-5);
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        skipSeconds(5);
      } else if (e.code === 'KeyM') {
        e.preventDefault();
        toggleMute();
      } else if (e.code === 'KeyF') {
        e.preventDefault();
        toggleFullscreen();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [togglePlay]);

  const progressPercent = effectiveDuration > 0 ? (currentTime / effectiveDuration) * 100 : 0;
  const bufferPercent = effectiveDuration > 0 ? (bufferedEnd / effectiveDuration) * 100 : 0;

  return (
    <div
      ref={containerRef}
      onMouseMove={handleUserActivity}
      onMouseEnter={() => setShowControls(true)}
      onMouseLeave={() => {
        if (isPlaying) setShowControls(false);
      }}
      style={{
        position: 'relative',
        width: '100%',
        background: '#000000',
        borderRadius: isFullscreen ? '0px' : '12px',
        overflow: 'hidden',
        boxShadow: '0 10px 40px rgba(0, 0, 0, 0.6)',
        userSelect: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      <video
        ref={videoRef}
        playsInline
        preload="auto"
        onClick={togglePlay}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => {
          setIsPlaying(true);
          setIsBuffering(false);
          handleUserActivity();
        }}
        onPause={() => {
          setIsPlaying(false);
          setShowControls(true);
        }}
        onEnded={() => {
          setIsPlaying(false);
          setShowControls(true);
        }}
        onWaiting={() => setIsBuffering(true)}
        onPlaying={() => setIsBuffering(false)}
        style={{
          width: '100%',
          display: 'block',
          maxHeight: isFullscreen ? '100vh' : '500px',
          background: '#000',
          cursor: 'pointer'
        }}
      >
        <source src={src} type="video/webm" />
        <source src={src} type="video/mp4" />
        Tu navegador no soporta la reproducción de video HTML5.
      </video>

      {/* Botón Central de Play cuando está pausado */}
      {!isPlaying && !isBuffering && (
        <div
          onClick={togglePlay}
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.3)',
            cursor: 'pointer',
            transition: 'background 0.2s ease'
          }}
        >
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 24px rgba(79, 70, 229, 0.5)',
              transform: 'scale(1)',
              transition: 'transform 0.15s ease'
            }}
          >
            <span style={{ fontSize: '24px', marginLeft: '3px' }}>▶</span>
          </div>
        </div>
      )}

      {/* Indicador de buffering */}
      {isBuffering && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.45)',
            pointerEvents: 'none',
            gap: '10px'
          }}
        >
          <div
            style={{
              width: '42px',
              height: '42px',
              border: '3px solid rgba(129, 140, 248, 0.25)',
              borderTopColor: '#818cf8',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite'
            }}
          />
          <span style={{ fontSize: '12px', color: '#cbd5e1' }}>Cargando fragmento...</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* Barra de Controles Inferior */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          background: 'linear-gradient(to top, rgba(15, 23, 42, 0.95) 0%, rgba(15, 23, 42, 0.65) 60%, transparent 100%)',
          padding: '16px 18px 12px 18px',
          opacity: showControls || !isPlaying ? 1 : 0,
          pointerEvents: showControls || !isPlaying ? 'auto' : 'none',
          transition: 'opacity 0.25s ease',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}
      >
        {/* Barra de Progreso y Scrubber */}
        <div
          ref={progressBarRef}
          onMouseDown={handleProgressBarMouseDown}
          onMouseMove={handleProgressHover}
          onMouseLeave={() => setHoverTime(null)}
          style={{
            position: 'relative',
            width: '100%',
            height: '8px',
            background: 'rgba(255, 255, 255, 0.2)',
            borderRadius: '999px',
            cursor: 'pointer',
            padding: '2px 0'
          }}
        >
          {/* Buffer */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: 0,
              width: `${Math.min(100, bufferPercent)}%`,
              background: 'rgba(255, 255, 255, 0.3)',
              borderRadius: '999px',
              pointerEvents: 'none'
            }}
          />

          {/* Progreso actual */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: 0,
              width: `${Math.min(100, Math.max(0, progressPercent))}%`,
              background: 'linear-gradient(90deg, #6366f1 0%, #818cf8 100%)',
              borderRadius: '999px',
              pointerEvents: 'none'
            }}
          />

          {/* Manija del Scrubber */}
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: `${Math.min(100, Math.max(0, progressPercent))}%`,
              transform: 'translate(-50%, -50%)',
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              background: '#ffffff',
              boxShadow: '0 2px 6px rgba(0, 0, 0, 0.4)',
              pointerEvents: 'none'
            }}
          />

          {/* Tooltip de Hover */}
          {hoverTime !== null && (
            <div
              style={{
                position: 'absolute',
                bottom: '16px',
                left: `${hoverPosition}px`,
                transform: 'translateX(-50%)',
                background: 'rgba(15, 23, 42, 0.95)',
                color: '#f8fafc',
                fontSize: '11px',
                fontWeight: 600,
                padding: '3px 7px',
                borderRadius: '4px',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
              }}
            >
              {formatTime(hoverTime)}
            </div>
          )}
        </div>

        {/* Fila de Botones y Tiempo */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '13px'
          }}
        >
          {/* Lado izquierdo: Play/Pausa, +/- 5s y Tiempos */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              type="button"
              onClick={togglePlay}
              aria-label={isPlaying ? 'Pausar' : 'Reproducir'}
              style={{
                background: 'rgba(255, 255, 255, 0.12)',
                border: 'none',
                borderRadius: '6px',
                color: '#ffffff',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              {isPlaying ? '⏸' : '▶'}
            </button>

            {/* Retroceder 5 segundos */}
            <button
              type="button"
              onClick={() => skipSeconds(-5)}
              title="Retroceder 5 segundos (←)"
              style={{
                background: 'transparent',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                color: '#cbd5e1',
                padding: '4px 8px',
                fontSize: '11.5px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              ↺ 5s
            </button>

            {/* Avanzar 5 segundos */}
            <button
              type="button"
              onClick={() => skipSeconds(5)}
              title="Avanzar 5 segundos (→)"
              style={{
                background: 'transparent',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                color: '#cbd5e1',
                padding: '4px 8px',
                fontSize: '11.5px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              5s ↻
            </button>

            {/* Indicador de Tiempo Real: Tiempo Actual / Tiempo Total */}
            <div style={{ display: 'flex', alignItems: 'center', marginLeft: '6px' }}>
              <span
                style={{
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: '13px',
                  fontVariantNumeric: 'tabular-nums',
                  letterSpacing: '0.2px'
                }}
              >
                {formatTime(currentTime)}
              </span>
              <span style={{ color: 'rgba(255, 255, 255, 0.45)', margin: '0 5px', fontSize: '13px' }}>/</span>
              <span
                style={{
                  color: '#94a3b8',
                  fontSize: '13px',
                  fontWeight: 600,
                  fontVariantNumeric: 'tabular-nums',
                  letterSpacing: '0.2px'
                }}
              >
                {effectiveDuration > 0 ? formatTime(effectiveDuration) : '--:--'}
              </span>
            </div>
          </div>

          {/* Lado derecho: Volumen, Velocidad y Pantalla completa */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Control de Volumen */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <button
                type="button"
                onClick={toggleMute}
                aria-label={isMuted ? 'Activar sonido' : 'Silenciar'}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  fontSize: '15px',
                  padding: '4px'
                }}
              >
                {isMuted || volume === 0 ? '🔇' : volume < 0.5 ? '🔉' : '🔊'}
              </button>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                style={{
                  width: '60px',
                  height: '4px',
                  accentColor: '#818cf8',
                  cursor: 'pointer'
                }}
              />
            </div>

            {/* Selector de velocidad de reproducción */}
            <button
              type="button"
              onClick={cyclePlaybackRate}
              title="Velocidad de reproducción"
              style={{
                background: playbackRate !== 1 ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.08)',
                border: `1px solid ${playbackRate !== 1 ? 'rgba(129, 140, 248, 0.4)' : 'rgba(255, 255, 255, 0.12)'}`,
                borderRadius: '6px',
                color: playbackRate !== 1 ? '#a5b4fc' : '#cbd5e1',
                padding: '4px 8px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                letterSpacing: '0.3px'
              }}
            >
              {playbackRate}x
            </button>

            {/* Pantalla completa */}
            <button
              type="button"
              onClick={toggleFullscreen}
              aria-label={isFullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
              title="Pantalla completa (F)"
              style={{
                background: 'transparent',
                border: 'none',
                color: '#cbd5e1',
                cursor: 'pointer',
                fontSize: '15px',
                padding: '4px'
              }}
            >
              {isFullscreen ? '⤦' : '⛶'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

