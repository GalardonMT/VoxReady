'use client';

import React, { useEffect, useState } from 'react';
import type { Microlesson } from '../../types/api';
import { microlessonService } from '../../services/microlessonService';
import { practiceScenario, shouldShowVideo } from '../../services/microlessonRules';

interface LessonViewProps {
  lessonReference?: string;
  onBack: () => void;
  onPracticeScenario: (scenarioId: string) => void;
}

const causeMessage = (cause: unknown) => cause instanceof Error ? cause.message : 'No se pudieron cargar las microlecciones.';

export const LessonView: React.FC<LessonViewProps> = ({ lessonReference, onBack, onPracticeScenario }) => {
  const [items, setItems] = useState<Microlesson[]>([]);
  const [selected, setSelected] = useState<Microlesson | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [videoLoading, setVideoLoading] = useState(false);

  useEffect(() => {
    let active = true; setLoading(true); setError('');
    microlessonService.list().then(list => {
      if (!active) return;
      setItems(list);
      if (lessonReference) {
        const needle = lessonReference.toLocaleLowerCase();
        const match = list.find(item => item.id === lessonReference || item.topicTag?.toLocaleLowerCase() === needle || item.title.toLocaleLowerCase() === needle);
        setSelected(match ?? null);
      } else setSelected(null);
    }).catch(cause => { if (active) setError(causeMessage(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [lessonReference]);

  useEffect(() => {
    setVideoUrl('');
    if (!selected || !shouldShowVideo(selected)) return;
    let active = true; setVideoLoading(true);
    microlessonService.playbackUrl(selected.id).then(url => { if (active) setVideoUrl(url); })
      .catch(cause => { if (active) setError(causeMessage(cause)); })
      .finally(() => { if (active) setVideoLoading(false); });
    return () => { active = false; };
  }, [selected]);

  if (loading) return <div className="canvas-content"><p role="status">Cargando microlecciones…</p></div>;
  if (!selected) return <div className="canvas-content">
    <div className="master-heading"><div><h2>Microlecciones</h2><p className="legend">Técnicas breves para preparar tu próxima práctica. No son evaluadas.</p></div><button type="button" className="btn ghost" onClick={onBack}>Volver</button></div>
    {error && <p role="alert" className="master-error">{error}</p>}
    {items.length === 0 ? <div className="card"><p>No hay microlecciones activas disponibles para tu empresa.</p></div> :
      <div className="grid3">{items.map(item => <article className="card microlesson-card" key={item.id}>
        <div className="master-pills">{item.topicTag && <span className="tagm">{item.topicTag}</span>}{item.durationMinutes && <span className="tagm">≈ {item.durationMinutes} min</span>}{item.hasVideo && <span className="tagm">▶ Video</span>}</div>
        <h3>{item.title}</h3><p>{item.learningObjective}</p><div className="legend">Escenario: {item.scenarioTitle}</div>
        <button type="button" className="btn pri" onClick={() => setSelected(item)}>Abrir microlección</button>
      </article>)}</div>}
  </div>;

  return <div className="canvas-content">
    <button type="button" className="btn ghost" onClick={() => setSelected(null)}>← Todas las microlecciones</button>
    {error && <p role="alert" className="master-error">{error}</p>}
    <article className="card microlesson-detail">
      <div className="master-heading"><div><div className="master-pills">{selected.topicTag && <span className="tagm">{selected.topicTag}</span>}{selected.durationMinutes && <span className="tagm">≈ {selected.durationMinutes} min</span>}</div><h2>{selected.title}</h2></div></div>
      <section><h3>Qué aprenderás</h3><p>{selected.learningObjective}</p></section>
      <section><h3>Explicación</h3><div className="microlesson-copy">{selected.theoryContent}</div></section>
      {shouldShowVideo(selected) && <section><h3>Video</h3>{videoLoading ? <p role="status">Preparando acceso seguro al video…</p> : videoUrl ? <video className="microlesson-player" controls preload="metadata" src={videoUrl}>Tu navegador no puede reproducir este video.</video> : null}</section>}
      {selected.exampleContent && <section><h3>Ejemplo comentado</h3><div className="area microlesson-copy">{selected.exampleContent}</div></section>}
      <div className="microlesson-practice"><div><strong>Escenario relacionado</strong><div className="legend">{selected.scenarioTitle}</div></div><button type="button" className="btn pri" onClick={() => onPracticeScenario(practiceScenario(selected))}>Practicar un escenario aplicando esta técnica</button></div>
    </article>
  </div>;
};
