'use client';

import React, { useState, useEffect, useRef } from 'react';
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

  const videoRef = useRef<HTMLVideoElement>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [lightLevel, setLightLevel] = useState(0);

  useEffect(() => {
    let isMounted = true;
    let stream: MediaStream | null = null;
    let audioContext: AudioContext | null = null;
    let animationFrameId: number;

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

        // Setup audio analyzer
        audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(s);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);

        // Setup video analyzer for lighting (using a small off-screen canvas)
        const canvas = document.createElement('canvas');
        canvas.width = 32;
        canvas.height = 32;
        const ctx = canvas.getContext('2d');

        let frameCount = 0;

        const analyzeStream = () => {
          if (!isMounted) return;
          
          // Audio level
          analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
          }
          const averageAudio = sum / dataArray.length;
          const newMicLevel = Math.min(100, Math.round((averageAudio / 80) * 100));
          setMicLevel(newMicLevel);

          // Video lighting level (sample every 10 frames to save CPU)
          frameCount++;
          if (frameCount % 10 === 0 && videoRef.current && ctx && videoRef.current.videoWidth > 0) {
            ctx.drawImage(videoRef.current, 0, 0, 32, 32);
            const imageData = ctx.getImageData(0, 0, 32, 32);
            const data = imageData.data;
            let totalLuminance = 0;
            
            // Iterate over all pixels (RGBA)
            for (let i = 0; i < data.length; i += 4) {
              const r = data[i];
              const g = data[i + 1];
              const b = data[i + 2];
              // Standard relative luminance formula
              const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
              totalLuminance += luminance;
            }
            
            const averageLuminance = totalLuminance / (32 * 32);
            // Convert to percentage (0 = black, 255 = white)
            // Boost it slightly so a normally lit room looks like ~70-80%
            const newLightLevel = Math.min(100, Math.round((averageLuminance / 200) * 100));
            setLightLevel(newLightLevel);
          }

          animationFrameId = requestAnimationFrame(analyzeStream);
        };
        analyzeStream();

      } catch (err: any) {
        if (isMounted) {
          setStreamError('Error al acceder a la cámara o micrófono: ' + err.message);
        }
      }
    }
    setupCamera();

    return () => {
      isMounted = false;
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
      if (audioContext && audioContext.state !== 'closed') {
        audioContext.close();
      }
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, []);

  const isEnabled = chk1 && chk2;

  return (
    <div className="canvas-content">
      <div className="row">
        {/* Left Column: Tech validation */}
        <div className="card col">
          <div className="label">{d.camL}</div>
          <div className="self" style={{ minHeight: '220px', position: 'relative', overflow: 'hidden' }}>
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
            <div
              style={{
                background: 'rgba(0, 0, 0, 0.5)',
                color: '#fff',
                position: 'absolute',
                bottom: '10px',
                left: '10px',
                zIndex: 10,
                padding: '4px 10px',
                borderRadius: '20px',
                fontSize: '11px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <i style={{ background: streamError ? 'var(--danger)' : 'var(--success)', width: '8px', height: '8px', borderRadius: '50%', display: 'inline-block' }} />
              <span>{streamError ? 'Error' : d.camOk}</span>
            </div>
          </div>

          <div style={{ marginTop: '16px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12.5px',
                marginBottom: '6px'
              }}
            >
              <span>🎤 {d.mic}</span>
              <span style={{ color: 'var(--success)', fontWeight: 600 }}>{d.micOk}</span>
            </div>
            <div className="meter">
              <i style={{ width: `${Math.max(5, micLevel)}%`, background: 'var(--success)', transition: 'width 0.1s ease-out' }} />
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: '12.5px',
                margin: '14px 0 6px'
              }}
            >
              <span>💡 {d.light}</span>
              <span style={{ color: '#ba7517', fontWeight: 600 }}>{d.lightW}</span>
            </div>
            <div className="meter">
              <i style={{ width: `${Math.max(5, lightLevel)}%`, background: '#ba7517', transition: 'width 0.3s ease-out' }} />
            </div>
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
