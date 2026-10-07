'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { masterTopicLabels as labels, masterTopicService as service } from '../../services/masterTopicService';
import type { LifecycleStatus, MasterTopicListItem } from '../../types/api';

interface Props { onEdit: (topicId: string | null) => void }

export function TopicCatalogView({ onEdit }: Props) {
  const { t } = useI18n();
  const d = t.masterTopics;
  const [topics, setTopics] = useState<MasterTopicListItem[]>([]);
  const [filter, setFilter] = useState<LifecycleStatus | 'all'>('active');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<MasterTopicListItem | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    service.topics('all').then(items => { if (active) setTopics(items); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : d.error); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision, d.error]);

  const changeStatus = async (topic: MasterTopicListItem, status: LifecycleStatus) => {
    setPending(topic.id); setError('');
    try {
      await service.topicStatus(topic.id, status);
      setArchiveTarget(null); setLoading(true); setRevision(value => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : d.error); }
    finally { setPending(null); }
  };

  const activeTopics = topics.filter(topic => topic.status === 'active');
  const clients = new Set(activeTopics.flatMap(topic => topic.clients.map(client => client.id)));
  const visible = topics.filter(topic => filter === 'all' || topic.status === filter);

  return <div className="canvas-content">
    <div className="master-heading">
      <h2>{d.catalog}</h2>
      <button type="button" className="btn pri" disabled={pending !== null} onClick={() => onEdit(null)}>{d.newTopic}</button>
    </div>
    <div className="grid3" style={{ marginBottom: 20 }}>
      {[[d.activeTopics, activeTopics.length], [d.availableScenarios, activeTopics.reduce((n, topic) => n + topic.scenarioCount, 0)], [d.coveredClients, clients.size]].map(([label, value]) =>
        <div className="stat" key={label}><div className="k">{label}</div><div className="v">{loading ? '…' : value}</div></div>)}
    </div>
    <div className="master-heading">
      <div className="master-pills">
        {(['active', 'archived', 'all'] as const).map(status => <button type="button" className={`pill ${filter === status ? 'on' : ''}`} aria-pressed={filter === status} key={status} onClick={() => setFilter(status)}>{d[status]}</button>)}
      </div>
    </div>
    {error && <p role="alert" className="master-error">{error}</p>}
    {loading ? <p role="status">{d.loading}</p> : visible.length === 0 ? <p>{d.empty}</p> :
      <div className="card" style={{ overflowX: 'auto' }}><table className="master-table">
        <thead><tr>{[d.topic, d.parameters, d.bank, d.scenarios, d.actions].map(title => <th scope="col" key={title}>{title}</th>)}</tr></thead>
        <tbody>{visible.map(topic => <tr key={topic.id}>
          <td style={{ minWidth: 220 }}><strong>{topic.name}</strong> <span className="tagm">{labels.status[topic.status]}</span><p className="master-preview">{topic.context}</p></td>
          <td><span className="tagm">{labels.optics[topic.optics]}</span> <span className="tagm">{labels.audience[topic.audience]}</span></td>
          <td>{topic.questionCount}</td>
          <td>{topic.scenarioCount}<div className="master-pills">{topic.clients.map(client => <span className="tagm" key={client.id}>{client.name}</span>)}</div></td>
          <td><div className="master-pills">
            <button type="button" className="btn ghost" disabled={pending !== null} onClick={() => onEdit(topic.id)}>✏️ {d.edit}</button>
            <button type="button" className="btn ghost" disabled={pending !== null} onClick={() => topic.status === 'active' ? setArchiveTarget(topic) : void changeStatus(topic, 'active')}>
              {pending === topic.id ? d.saving : topic.status === 'active' ? `📦 ${d.archive}` : `🔄 ${d.reactivate}`}
            </button>
          </div></td>
        </tr>)}</tbody>
      </table></div>}
    {archiveTarget && <ArchiveDialog title={archiveTarget.name} message={d.confirmArchive} error={error}
      busy={pending !== null} cancel={d.cancel} confirm={d.archive}
      onCancel={() => setArchiveTarget(null)} onConfirm={() => void changeStatus(archiveTarget, 'archived')} />}
  </div>;
}

function ArchiveDialog(props: { title: string; message: string; error: string; busy: boolean; cancel: string; confirm: string; onCancel: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const node = dialog.current; node?.showModal(); return () => node?.close(); }, []);
  return <dialog ref={dialog} className="master-dialog" aria-labelledby="archive-title" onCancel={event => { event.preventDefault(); if (!props.busy) props.onCancel(); }}>
    <h3 id="archive-title">{props.title}</h3><p>{props.message}</p>
    {props.error && <p role="alert" className="master-error">{props.error}</p>}
    <div className="master-pills"><button autoFocus type="button" className="btn ghost" disabled={props.busy} onClick={props.onCancel}>{props.cancel}</button>
      <button type="button" className="btn pri" disabled={props.busy} onClick={props.onConfirm}>{props.confirm}</button></div>
  </dialog>;
}
