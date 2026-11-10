'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RecordingVideoPlayer } from '../spokesperson/RecordingVideoPlayer';
import { labelingService } from '../../services/labelingService';
import {
  canRetryRecording,
  recordingDuration,
  recordingFailure,
  recordingRefreshDelay,
  validateRecordingTicket,
} from '../../services/labelingRecordingModel';
import type { LabelingRecordingTicket } from '../../types/api';

interface LabelingRecordingPlayerProps {
  caseId: string;
  availability: 'available' | 'unavailable';
  persistedDuration: number | null;
}

export function LabelingRecordingPlayer({
  caseId,
  availability,
  persistedDuration,
}: LabelingRecordingPlayerProps) {
  const [ticket, setTicket] = useState<LabelingRecordingTicket | null>(null);
  const [loading, setLoading] = useState(availability === 'available');
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const [resumePosition, setResumePosition] = useState(0);
  const positionRef = useRef(0);
  const attemptsRef = useRef(0);
  const mountedRef = useRef(true);

  const loadTicket = useCallback(async (signal?: AbortSignal, resetAttempts = false) => {
    setLoading(true);
    try {
      const issued = await labelingService.getRecordingTicket(caseId, signal);
      const invalid = validateRecordingTicket(issued);
      if (invalid) throw new Error(invalid);
      if (!mountedRef.current) return;
      if (resetAttempts) attemptsRef.current = 0;
      setResumePosition(positionRef.current);
      setTicket(issued);
      setGeneration(value => value + 1);
      setError(null);
    } catch (loadError) {
      if (signal?.aborted || !mountedRef.current) return;
      setError(recordingFailure(loadError).message);
    } finally {
      if (mountedRef.current && !signal?.aborted) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    mountedRef.current = true;
    positionRef.current = 0;
    attemptsRef.current = 0;
    if (availability !== 'available') {
      return () => { mountedRef.current = false; };
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => void loadTicket(controller.signal, true), 0);
    return () => {
      mountedRef.current = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [availability, loadTicket]);

  useEffect(() => {
    if (!ticket) return;
    const delay = recordingRefreshDelay(ticket.expiresAt, Date.now());
    const timer = window.setTimeout(() => {
      if (document.visibilityState === 'visible') void loadTicket(undefined, true);
    }, Math.min(delay, 2_147_000_000));
    const handleVisibility = () => {
      if (document.visibilityState === 'visible'
        && recordingRefreshDelay(ticket.expiresAt, Date.now()) === 0) {
        void loadTicket(undefined, true);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [loadTicket, ticket]);

  const recoverPlayback = async () => {
    if (!canRetryRecording(attemptsRef.current)) {
      setError('No fue posible reproducir la grabación después de renovar el acceso temporal.');
      return;
    }
    attemptsRef.current += 1;
    setError('La URL temporal expiró o se interrumpió. Renovando acceso…');
    await loadTicket();
  };

  if (availability !== 'available') {
    return <RecordingState message="La grabación fue eliminada, archivada o no quedó sellada para este caso." />;
  }

  if (!ticket && loading) return <RecordingState message="Cargando grabación segura…" busy />;
  if (!ticket) {
    return (
      <RecordingState message={error ?? 'No fue posible cargar la grabación.'}>
        <button type="button" className="btn ghost" onClick={() => void loadTicket(undefined, true)}>Reintentar</button>
      </RecordingState>
    );
  }

  return (
    <div>
      <RecordingVideoPlayer
        key={`${ticket.etag}:${generation}`}
        src={ticket.url}
        contentType={ticket.contentType}
        expectedDuration={recordingDuration(ticket, persistedDuration)}
        initialPosition={resumePosition}
        onPositionChange={seconds => { positionRef.current = seconds; }}
        onPlaybackError={() => void recoverPlayback()}
      />
      {(loading || error) && (
        <div role={error ? 'alert' : 'status'} style={{ fontSize: '11px', color: error ? 'var(--accent2)' : 'var(--muted)', marginTop: '6px' }}>
          {loading ? 'Renovando acceso temporal…' : error}
        </div>
      )}
    </div>
  );
}

function RecordingState({ message, busy = false, children }: {
  message: string;
  busy?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="vid" role={busy ? 'status' : 'alert'} style={{ minHeight: '210px', display: 'grid', placeItems: 'center', padding: '18px', textAlign: 'center' }}>
      <div style={{ color: '#fff' }}>
        <div style={{ fontSize: '28px', marginBottom: '8px' }}>{busy ? '◌' : '⚠'}</div>
        <div style={{ fontSize: '12px', marginBottom: '10px' }}>{message}</div>
        {children}
      </div>
    </div>
  );
}
