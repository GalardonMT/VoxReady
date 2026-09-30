'use client';

import React, { useEffect, useRef, useState } from 'react';
import { sessionFlowService, type SessionSetup } from '../../services/sessionFlowService';
import { ApiError } from '../../services/apiClient';
import { mediaErrorMessage, requestAudioAndVideo, stopMediaStream, trackAvailable } from '../../services/mediaCheck';

interface Props {
  setup: SessionSetup;
  onBegin: () => void;
  onCancel: () => void;
}

export const TechConsentView: React.FC<Props> = ({ setup, onBegin, onCancel }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const requestRef = useRef(0);
  const [cameraReady, setCameraReady] = useState(false);
  const [microphoneReady, setMicrophoneReady] = useState(false);
  const [checked, setChecked] = useState(false);
  const [checking, setChecking] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [microphoneError, setMicrophoneError] = useState('');
  const [acceptRecording, setAcceptRecording] = useState(false);
  const [acknowledgeDeletion, setAcknowledgeDeletion] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [consentError, setConsentError] = useState('');
  const [policy, setPolicy] = useState(setup.retentionPolicy);

  const stopTracks = () => {
    stopMediaStream(streamRef.current);
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraReady(false);
    setMicrophoneReady(false);
  };

  useEffect(() => {
    const request = requestRef;
    return () => {
      request.current += 1;
      stopMediaStream(streamRef.current);
      streamRef.current = null;
    };
  }, []);

  const checkDevices = async () => {
    const requestId = ++requestRef.current;
    stopTracks();
    setChecked(false);
    setChecking(true);
    setCameraError('');
    setMicrophoneError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      const message = 'El navegador no permite acceder a dispositivos aquí. Abre la aplicación mediante HTTPS o localhost.';
      setCameraError(message);
      setMicrophoneError(message);
      setChecked(true);
      setChecking(false);
      return;
    }
    try {
      const result = await requestAudioAndVideo(navigator.mediaDevices, () => requestId === requestRef.current);
      if (!result) return;
      const stream = new MediaStream([
        ...(result.audio?.getAudioTracks() ?? []),
        ...(result.video?.getVideoTracks() ?? []),
      ]);
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      const update = () => {
        const video = stream.getVideoTracks().some(trackAvailable);
        const audio = stream.getAudioTracks().some(trackAvailable);
        setCameraReady(video);
        setMicrophoneReady(audio);
        setCameraError(video ? '' : result.videoError
          ? mediaErrorMessage(result.videoError, 'camera')
          : 'Se perdió el acceso a la cámara. Repite la comprobación.');
        setMicrophoneError(audio ? '' : result.audioError
          ? mediaErrorMessage(result.audioError, 'microphone')
          : 'Se perdió el acceso al micrófono. Repite la comprobación.');
      };
      stream.getTracks().forEach((track) => {
        track.addEventListener('ended', update);
        track.addEventListener('mute', update);
        track.addEventListener('unmute', update);
      });
      update();
      setChecked(true);
    } catch (cause) {
      if (requestId !== requestRef.current) return;
      const message = cause instanceof Error ? cause.message : 'No se pudo comprobar los dispositivos.';
      setCameraError(message);
      setMicrophoneError(message);
      setChecked(true);
    } finally {
      if (requestId === requestRef.current) setChecking(false);
    }
  };

  const ready = cameraReady && microphoneReady && acceptRecording && acknowledgeDeletion && !checking && !submitting && setup.status === 'created';
  const begin = async () => {
    if (!ready) return;
    setSubmitting(true);
    setConsentError('');
    try {
      await sessionFlowService.grantConsent(setup.sessionId, policy.version);
      stopTracks();
      onBegin();
    } catch (cause) {
      if (cause instanceof ApiError && cause.problem.title === 'policy_version_changed') {
        try {
          const updated = await sessionFlowService.getSession(setup.sessionId);
          setPolicy(updated.retentionPolicy);
          setAcceptRecording(false);
          setAcknowledgeDeletion(false);
        } catch { /* Keep the API error visible and allow the user to retry. */ }
      }
      setConsentError(cause instanceof Error ? cause.message : 'No se pudo registrar el consentimiento.');
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="canvas-content"><div className="row">
    <div className="card col">
      <div className="label">Comprobación técnica</div>
      <div className="self" style={{ minHeight: 220 }}>
        <video ref={videoRef} autoPlay playsInline muted aria-label="Vista previa de cámara"
          style={{ width: '100%', maxHeight: 300, objectFit: 'contain' }} />
      </div>
      <p role="status">Cámara: {!checked ? 'sin comprobar' : cameraReady ? 'disponible' : 'no disponible'} · Micrófono: {!checked ? 'sin comprobar' : microphoneReady ? 'disponible' : 'no disponible'}</p>
      {cameraError && <p role="alert" style={{ color: 'var(--danger)' }}>{cameraError}</p>}
      {microphoneError && <p role="alert" style={{ color: 'var(--danger)' }}>{microphoneError}</p>}
      <button type="button" className="btn" disabled={checking || submitting} onClick={() => void checkDevices()}>
        {checking ? 'Solicitando permisos…' : 'Comprobar cámara y micrófono'}
      </button>
    </div>
    <div className="card col">
      <div className="label">Consentimiento de grabación y tratamiento biométrico</div>
      <p>Se grabarán voz e imagen para evaluar tu práctica. Dar permisos al navegador solo habilita los dispositivos; el consentimiento se registra por separado.</p>
      <p>Política de retención de tu empresa: versión {policy.version}. {policy.keep === 'full_recording'
        ? `Grabación conservada durante ${policy.termDays} días.`
        : 'Solo se conservan métricas.'}</p>
      <label style={{ display: 'block', margin: '12px 0' }}>
        <input type="checkbox" checked={acceptRecording} onChange={(event) => setAcceptRecording(event.target.checked)} />{' '}
        Consiento la grabación de mi voz e imagen y su tratamiento para esta sesión conforme a la política indicada.
      </label>
      <label style={{ display: 'block', margin: '12px 0' }}>
        <input type="checkbox" checked={acknowledgeDeletion} onChange={(event) => setAcknowledgeDeletion(event.target.checked)} />{' '}
        Entiendo que puedo solicitar el borrado de mis grabaciones.
      </label>
      {consentError && <p role="alert" style={{ color: 'var(--danger)' }}>{consentError}</p>}
      <div style={{ display: 'flex', gap: 10 }}>
        <button type="button" className="btn pri" disabled={!ready} onClick={() => void begin()}>
          {submitting ? 'Registrando consentimiento…' : 'Comenzar sesión'}
        </button>
        <button type="button" className="btn ghost" onClick={() => { requestRef.current += 1; stopTracks(); onCancel(); }}>Cancelar</button>
      </div>
      {!ready && !submitting && <p id="begin-requirements" className="legend" style={{ marginTop: 10 }}>
        Para comenzar necesitas cámara y micrófono disponibles, además de ambas casillas de consentimiento.
      </p>}
    </div>
  </div></div>;
};
