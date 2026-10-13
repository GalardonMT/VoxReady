'use client';

import React, { useEffect, useState } from 'react';
import type { ClientInfo, LifecycleStatus, Microlesson, MicrolessonInput, MicrolessonScenario } from '../../types/api';
import { masterMicrolessonService } from '../../services/microlessonService';
import { withClient } from '../../services/microlessonRules';
import { ApiError, NetworkError } from '../../services/apiClient';

const emptyForm: MicrolessonInput = {
  clientId: '', scenarioId: '', title: '', topicTag: '', durationMinutes: null,
  learningObjective: '', theoryContent: '', exampleContent: '', status: 'active',
};
const errorMessage = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback;
const loadErrorMessage = (cause: unknown) => {
  if (cause instanceof NetworkError) return 'La API no está disponible. Comprueba el entorno local y vuelve a intentar.';
  if (cause instanceof ApiError) {
    if (cause.problem.status === 401) return 'La sesión no es válida. Inicia sesión nuevamente.';
    if (cause.problem.status === 403 && cause.message.toLowerCase().includes('no registrado')) {
      return 'Usuario no registrado en VoxReady.';
    }
    if (cause.problem.status === 403) return 'Tu usuario no tiene permisos para administrar microlecciones.';
    return cause.message || `La API respondió con un error (${cause.problem.status}).`;
  }
  return 'Ocurrió un error inesperado al cargar las microlecciones.';
};

export const MicrolessonManagerView: React.FC = () => {
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [lessons, setLessons] = useState<Microlesson[]>([]);
  const [clientFilter, setClientFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<LifecycleStatus | 'all'>('all');
  const [editing, setEditing] = useState<Microlesson | 'new' | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'success' | 'error'>('loading');
  const [loadError, setLoadError] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const reload = async () => {
    setLoadState('loading'); setLoadError('');
    try {
      const [availableClients, availableLessons] = await Promise.all([
        masterMicrolessonService.clients(),
        masterMicrolessonService.list({ clientId: clientFilter || undefined, status: statusFilter }),
      ]);
      setClients(availableClients);
      setLessons(availableLessons);
      setLoadState('success');
    } catch (cause) {
      setLoadError(loadErrorMessage(cause));
      setLoadState('error');
    }
  };

  useEffect(() => { void reload(); }, [clientFilter, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const changeStatus = async (lesson: Microlesson) => {
    const next = lesson.status === 'active' ? 'archived' : 'active';
    setBusyId(lesson.id); setError(''); setNotice('');
    try {
      await masterMicrolessonService.status(lesson.id, next);
      setNotice(next === 'active' ? 'Microlección reactivada.' : 'Microlección archivada.');
      await reload();
    } catch (cause) { setError(errorMessage(cause, 'No se pudo cambiar el estado.')); }
    finally { setBusyId(null); }
  };

  return <div className="canvas-content">
    <div className="master-heading">
      <div><h2>Gestión de microlecciones</h2><p className="legend">Contenido educativo por empresa y escenario. No forma parte de la evaluación.</p></div>
      <button type="button" className="btn pri" disabled={editing !== null || loadState !== 'success' || clients.length === 0} onClick={() => { setEditing('new'); setError(''); setNotice(''); }}>＋ Nueva microlección</button>
    </div>
    {loadError && <div className="master-error" role="alert"><p>{loadError}</p><button type="button" className="btn ghost" onClick={() => void reload()}>Reintentar</button></div>}
    {error && <p role="alert" className="master-error">{error}</p>}
    {notice && <p role="status" className="master-success">{notice}</p>}
    {editing && <MicrolessonEditor key={editing === 'new' ? 'new' : editing.id} clients={clients}
      existing={editing === 'new' ? undefined : editing} onCancel={() => setEditing(null)}
      onSaved={async saved => { setEditing(null); setNotice(`Microlección “${saved.title}” guardada correctamente.`); await reload(); }} />}

    <section className="card" aria-labelledby="microlesson-list-title">
      <div className="master-heading"><h3 id="microlesson-list-title">Microlecciones</h3><div className="master-filters">
        <label>Cliente<select className="field" disabled={loadState !== 'success'} value={clientFilter} onChange={e => setClientFilter(e.target.value)}><option value="">Todos</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
        <label>Estado<select className="field" disabled={loadState !== 'success'} value={statusFilter} onChange={e => setStatusFilter(e.target.value as LifecycleStatus | 'all')}><option value="all">Todos</option><option value="active">Activas</option><option value="archived">Archivadas</option></select></label>
      </div></div>
      {loadState === 'loading' ? <p role="status">Cargando microlecciones…</p> : loadState === 'error' ? null : lessons.length === 0 ? <p>No hay microlecciones para estos filtros.</p> :
        <div className="master-table-wrap"><table className="master-table"><thead><tr><th>Cliente</th><th>Escenario</th><th>Título y tema</th><th>Duración</th><th>Video</th><th>Estado</th><th>Acciones</th></tr></thead>
          <tbody>{lessons.map(lesson => <tr key={lesson.id}><td>{lesson.clientName}</td><td>{lesson.scenarioTitle}</td><td><strong>{lesson.title}</strong>{lesson.topicTag && <div className="legend">{lesson.topicTag}</div>}</td>
            <td>{lesson.durationMinutes ? `${lesson.durationMinutes} min` : '—'}</td><td>{lesson.hasVideo ? '✓ Sí' : '—'}</td><td><span className="tagm">{lesson.status === 'active' ? 'Activa' : 'Archivada'}</span></td>
            <td><div className="master-actions"><button type="button" className="btn ghost" disabled={!!busyId || !!editing} onClick={() => setEditing(lesson)}>Editar</button>
              <button type="button" className="btn ghost" disabled={!!busyId || !!editing} onClick={() => void changeStatus(lesson)}>{busyId === lesson.id ? 'Guardando…' : lesson.status === 'active' ? 'Archivar' : 'Reactivar'}</button></div></td>
          </tr>)}</tbody></table></div>}
    </section>
  </div>;
};

const MicrolessonEditor: React.FC<{ clients: ClientInfo[]; existing?: Microlesson; onCancel: () => void; onSaved: (lesson: Microlesson) => void; }> = ({ clients, existing, onCancel, onSaved }) => {
  const [form, setForm] = useState<MicrolessonInput>(existing ? {
    clientId: existing.clientId, scenarioId: existing.scenarioId, title: existing.title, topicTag: existing.topicTag ?? '', durationMinutes: existing.durationMinutes,
    learningObjective: existing.learningObjective, theoryContent: existing.theoryContent, exampleContent: existing.exampleContent ?? '', status: existing.status,
  } : emptyForm);
  const [scenarios, setScenarios] = useState<MicrolessonScenario[]>([]);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [persistedId, setPersistedId] = useState(existing?.id ?? '');
  const [hasVideo, setHasVideo] = useState(existing?.hasVideo ?? false);
  const [videoName, setVideoName] = useState(existing?.videoFileName ?? '');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!form.clientId) { setScenarios([]); return; }
    let active = true; setScenarioLoading(true);
    masterMicrolessonService.scenarios(form.clientId, existing ? 'all' : 'active').then(items => { if (active) setScenarios(items); })
      .catch(cause => { if (active) setError(errorMessage(cause, 'No se pudieron cargar los escenarios.')); })
      .finally(() => { if (active) setScenarioLoading(false); });
    return () => { active = false; };
  }, [form.clientId, existing]);

  const field = <K extends keyof MicrolessonInput>(key: K, value: MicrolessonInput[K]) => setForm(current => ({ ...current, [key]: value }));
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.clientId || !form.scenarioId || !form.title.trim() || !form.learningObjective.trim() || !form.theoryContent.trim()) {
      setError('Completa cliente, escenario, título, objetivo y explicación.'); return;
    }
    setBusy(true); setError(''); setUploadStatus('Guardando contenido…');
    try {
      let saved = await masterMicrolessonService.save({ ...form, title: form.title.trim(), topicTag: form.topicTag?.trim() || null,
        learningObjective: form.learningObjective.trim(), theoryContent: form.theoryContent.trim(), exampleContent: form.exampleContent?.trim() || null }, persistedId || undefined);
      setPersistedId(saved.id);
      if (file) {
        setUploadStatus('Subiendo video a Azure Blob Storage…');
        saved = await masterMicrolessonService.uploadVideo(saved.id, file);
        setHasVideo(true); setVideoName(saved.videoFileName ?? file.name); setFile(null);
      }
      setUploadStatus(''); onSaved(saved);
    } catch (cause) {
      setUploadStatus(''); setError(errorMessage(cause, 'No se pudo completar el guardado. Puedes reintentar sin perder los datos escritos.'));
    } finally { setBusy(false); }
  };

  const removeVideo = async () => {
    if (!persistedId) return;
    setBusy(true); setError(''); setUploadStatus('Retirando video…');
    try { await masterMicrolessonService.removeVideo(persistedId); setHasVideo(false); setVideoName(''); setConfirmRemove(false); setUploadStatus('Video retirado.'); }
    catch (cause) { setError(errorMessage(cause, 'No se pudo retirar el video.')); setUploadStatus(''); }
    finally { setBusy(false); }
  };

  return <form className="card microlesson-editor" onSubmit={save}>
    <div className="master-heading"><h3>{existing ? 'Editar microlección' : 'Crear microlección'}</h3><button type="button" className="btn ghost" disabled={busy} onClick={onCancel}>Cerrar</button></div>
    {error && <p role="alert" className="master-error">{error}</p>}{uploadStatus && <p role="status" className="master-success">{uploadStatus}</p>}
    <fieldset className="master-fieldset" disabled={busy}>
      <h4>Identificación</h4><div className="microlesson-grid">
        <label>Cliente o empresa *<select className="field" required value={form.clientId} onChange={e => setForm(current => withClient(current, e.target.value))}><option value="">Selecciona un cliente</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}{client.status === 'archived' ? ' (archivado)' : ''}</option>)}</select></label>
        <label>Escenario relacionado *<select className="field" required value={form.scenarioId} onChange={e => field('scenarioId', e.target.value)} disabled={!form.clientId || scenarioLoading}><option value="">{scenarioLoading ? 'Cargando…' : 'Selecciona un escenario'}</option>{scenarios.map(scenario => <option key={scenario.id} value={scenario.id} disabled={scenario.status === 'archived'}>{scenario.title}{scenario.status === 'archived' ? ' (archivado)' : ''}</option>)}</select></label>
        <label>Título *<input className="field" required maxLength={150} value={form.title} onChange={e => field('title', e.target.value)} /></label>
        <label>Tema o técnica<input className="field" maxLength={50} placeholder="Ej.: bridging" value={form.topicTag ?? ''} onChange={e => field('topicTag', e.target.value)} /></label>
        <label>Duración estimada (min)<input className="field" type="number" min={1} max={1440} value={form.durationMinutes ?? ''} onChange={e => field('durationMinutes', e.target.value ? Number(e.target.value) : null)} /></label>
        <label>Estado<select className="field" value={form.status} onChange={e => field('status', e.target.value as LifecycleStatus)}><option value="active">Activa</option><option value="archived">Archivada</option></select></label>
      </div>
      <h4>Contenido educativo</h4>
      <label>Qué aprenderá el vocero *<textarea className="field microlesson-textarea" required value={form.learningObjective} onChange={e => field('learningObjective', e.target.value)} /></label>
      <label>Explicación o teoría breve *<textarea className="field microlesson-textarea tall" required value={form.theoryContent} onChange={e => field('theoryContent', e.target.value)} /></label>
      <label>Ejemplo comentado o caso analizado<textarea className="field microlesson-textarea tall" value={form.exampleContent ?? ''} onChange={e => field('exampleContent', e.target.value)} /></label>
      <h4>Material audiovisual</h4>
      {hasVideo && <div className="microlesson-video-state"><span>✓ Video existente{videoName ? `: ${videoName}` : ''}</span><button type="button" className="btn ghost" onClick={() => setConfirmRemove(true)}>Retirar video</button></div>}
      {confirmRemove && <div className="microlesson-confirm" role="alertdialog" aria-label="Confirmar retiro de video"><p>¿Confirmas que deseas retirar el video existente? El contenido se conservará.</p><div className="master-actions"><button type="button" className="btn" onClick={() => setConfirmRemove(false)}>Cancelar</button><button type="button" className="btn pri" onClick={() => void removeVideo()}>Sí, retirar</button></div></div>}
      <label>{hasVideo ? 'Reemplazar video (opcional)' : 'Subir video (opcional)'}<input className="field" type="file" accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <p className="legend">{file ? `Archivo seleccionado: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)` : 'Formatos permitidos: MP4, WebM y MOV. Máximo 250 MB.'}</p>
      <div className="master-actions"><button type="button" className="btn" onClick={onCancel}>Cancelar</button><button type="submit" className="btn pri" disabled={busy}>{busy ? 'Guardando…' : 'Guardar microlección'}</button></div>
    </fieldset>
  </form>;
};
