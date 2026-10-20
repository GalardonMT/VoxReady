'use client';

import React, { useEffect, useRef, useState } from 'react';
import type { MicrolessonCatalog, SpokespersonMicrolesson, SpokespersonMicrolessonDetail } from '../../types/api';
import { microlessonService } from '../../services/microlessonService';
import { chooseLesson, groupMicrolessons } from '../../services/microlessonPresentation';
import { practiceScenario, shouldShowVideo } from '../../services/microlessonRules';

interface LessonViewProps {
  lessonReference?: string;
  onBack: () => void;
  onPracticeScenario: (scenarioId: string) => void;
}

const causeMessage = (cause: unknown) => cause instanceof Error ? cause.message : 'No se pudieron cargar las microlecciones.';
const emptyCatalog: MicrolessonCatalog = { items: [], history: [], total: 0 };

export const LessonView: React.FC<LessonViewProps> = ({ lessonReference, onBack, onPracticeScenario }) => {
  const [catalog, setCatalog] = useState<MicrolessonCatalog>(emptyCatalog);
  const [selected, setSelected] = useState<SpokespersonMicrolessonDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [videoLoading, setVideoLoading] = useState(false);
  const [retryItem, setRetryItem] = useState<SpokespersonMicrolesson | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const selectedId = selected?.id;
  const selectedHasVideo = selected?.hasVideo;

  const refreshCatalog = async () => setCatalog(await microlessonService.list());

  const openLesson = async (item: SpokespersonMicrolesson) => {
    if (!item.canOpen) return;
    setDetailLoading(true); setError(''); setVideoUrl('');
    try {
      const detail = await microlessonService.detail(item.id);
      setRetryItem(null);
      setVideoLoading(detail.hasVideo);
      if (detail.assignmentStatus === 'assigned') {
        const started = await microlessonService.start(item.id);
        setSelected({ ...detail, ...started });
        await refreshCatalog();
      } else setSelected(detail);
    } catch (cause) { setRetryItem(item); setError(causeMessage(cause)); }
    finally { setDetailLoading(false); }
  };

  useEffect(() => {
    let active = true;
    microlessonService.list().then(async result => {
      if (!active) return;
      setCatalog(result);
      if (lessonReference) {
        const item = chooseLesson(result.items, lessonReference);
        if (!item) { setError('Esta microlección no está asignada o ya no está disponible.'); return; }
        setDetailLoading(true);
        try {
          const detail = await microlessonService.detail(item.id);
          if (!active) return;
          setVideoLoading(detail.hasVideo);
          if (detail.assignmentStatus === 'assigned') {
            const started = await microlessonService.start(item.id);
            if (!active) return;
            setSelected({ ...detail, ...started });
            const refreshed = await microlessonService.list();
            if (active) setCatalog(refreshed);
          } else setSelected(detail);
        } catch (cause) { if (active) setError(causeMessage(cause)); }
        finally { if (active) setDetailLoading(false); }
      }
    }).catch(cause => { if (active) setError(causeMessage(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [lessonReference, retryNonce]);

  useEffect(() => {
    if (!selectedId || !selectedHasVideo) return;
    let active = true;
    const video = videoRef.current;
    microlessonService.playbackUrl(selectedId).then(url => { if (active) setVideoUrl(url); })
      .catch(cause => { if (active) setError(causeMessage(cause)); })
      .finally(() => { if (active) setVideoLoading(false); });
    return () => { active = false; video?.pause(); };
  }, [selectedId, selectedHasVideo]);

  const complete = async () => {
    if (!selected || selected.assignmentStatus !== 'in_progress' || busy) return;
    setBusy(true); setError('');
    try {
      const completed = await microlessonService.complete(selected.id);
      setSelected(current => current ? { ...current, ...completed } : current);
      await refreshCatalog();
    } catch (cause) { setError(causeMessage(cause)); }
    finally { setBusy(false); }
  };

  const restart = async () => {
    if (!selected || selected.assignmentStatus !== 'completed' || busy) return;
    setBusy(true); setError('');
    try {
      await microlessonService.restart(selected.id);
      const started = await microlessonService.start(selected.id);
      setSelected(current => current ? { ...current, ...started } : current);
      if (videoRef.current) { videoRef.current.currentTime = 0; }
      await refreshCatalog();
    } catch (cause) { setError(causeMessage(cause)); }
    finally { setBusy(false); }
  };

  const groups = groupMicrolessons(catalog.items, catalog.history);
  const sections = [
    { title: 'En progreso', items: groups.inProgress },
    { title: 'Asignadas', items: groups.assigned },
    { title: 'Completadas', items: groups.completed },
    { title: 'Catálogo de la empresa', items: groups.catalog },
    { title: 'Archivadas', items: groups.archived },
  ];

  return <div className="canvas-content">
    <div className="master-heading"><div><h2>Microlecciones</h2><p className="legend">Técnicas breves para preparar tu próxima práctica. No son evaluadas.</p></div><button type="button" className="btn ghost" onClick={onBack}>Volver</button></div>
    {error && <div role="alert" className="master-error"><p>{error}</p><button type="button" className="btn ghost" onClick={() => {
      setError('');
      if (retryItem) void openLesson(retryItem);
      else { setLoading(true); setRetryNonce(current => current + 1); }
    }}>Reintentar</button></div>}
    {(loading || detailLoading) && <p role="status">Cargando microlecciones…</p>}
    {!loading && !detailLoading && !selected && <>
      {!error && catalog.items.length === 0 && catalog.history.length === 0 && <div className="card"><p>No hay microlecciones activas disponibles para tu empresa.</p></div>}
      {sections.filter(section => section.items.length > 0).map(section => <section key={section.title} className="microlesson-section" aria-label={section.title}>
        <h3>{section.title}</h3>
        <div className="grid3">{section.items.map(item => <article className="card microlesson-card" key={item.assignmentId ?? item.id}>
          <div className="master-pills">{item.topicTag && <span className="tagm">{item.topicTag}</span>}{item.durationMinutes && <span className="tagm">≈ {item.durationMinutes} min</span>}{item.hasVideo && <span className="tagm">▶ Video</span>}</div>
          <h4>{item.title}</h4><p>{item.learningObjective}</p><div className="legend">Escenario: {item.scenarioTitle}</div>
          {item.completedAt && <div className="legend">Completada el {new Date(item.completedAt).toLocaleDateString('es-CL')}</div>}
          {item.revokedAt && <div className="legend">Archivada el {new Date(item.revokedAt).toLocaleDateString('es-CL')}</div>}
          {item.canOpen ? <button type="button" className="btn pri" onClick={() => void openLesson(item)}>Abrir microlección</button> : <span className="tagm">{section.title === 'Catálogo de la empresa' ? 'No asignada' : item.assignmentStatus === 'revoked' ? 'Asignación archivada' : item.status === 'archived' ? 'Microlección archivada' : item.assignmentStatus === 'completed' ? 'Ciclo anterior completado' : 'No asignada'}</span>}
        </article>)}</div>
      </section>)}
    </>}
    {!loading && !detailLoading && selected && <>
      <button type="button" className="btn ghost" onClick={() => { videoRef.current?.pause(); setSelected(null); setVideoUrl(''); }}>← Todas las microlecciones</button>
      <article className="card microlesson-detail">
        <div className="master-heading"><div><div className="master-pills">{selected.topicTag && <span className="tagm">{selected.topicTag}</span>}{selected.durationMinutes && <span className="tagm">≈ {selected.durationMinutes} min</span>}<span className="tagm">{selected.assignmentStatus === 'completed' ? 'Completada' : selected.assignmentStatus === 'in_progress' ? 'En progreso' : 'Asignada'}</span></div><h2>{selected.title}</h2></div></div>
        <section><h3>Qué aprenderás</h3><p>{selected.learningObjective}</p></section>
        <section><h3>Explicación</h3><div className="microlesson-copy">{selected.theoryContent}</div></section>
        {shouldShowVideo(selected) && <section><h3>Video</h3>{videoLoading ? <p role="status">Preparando acceso seguro al video…</p> : videoUrl ? <video ref={videoRef} className="microlesson-player" controls preload="metadata" src={videoUrl} onEnded={() => void complete()}>Tu navegador no puede reproducir este video.</video> : null}</section>}
        {selected.exampleContent && <section><h3>Ejemplo comentado</h3><div className="microlesson-copy">{selected.exampleContent}</div></section>}
        {selected.assignmentStatus === 'in_progress' && !selected.hasVideo && <button type="button" className="btn pri" disabled={busy} onClick={() => void complete()}>{busy ? 'Guardando…' : 'Marcar como completada'}</button>}
        {selected.assignmentStatus === 'completed' && <button type="button" className="btn" disabled={busy} onClick={() => void restart()}>{busy ? 'Preparando…' : 'Volver a realizar'}</button>}
        <div className="microlesson-practice"><div><strong>Escenario relacionado</strong><div className="legend">{selected.scenarioTitle}</div></div><button type="button" className="btn pri" disabled={!selected.canPractice} onClick={() => onPracticeScenario(practiceScenario(selected))}>Practicar escenario</button></div>
        {!selected.canPractice && <p className="legend">El escenario está archivado y no se puede practicar.</p>}
      </article>
    </>}
  </div>;
};
