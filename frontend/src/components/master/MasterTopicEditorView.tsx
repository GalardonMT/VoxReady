'use client';

import React, { useEffect, useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { masterTopicLabels as labels, masterTopicService as service } from '../../services/masterTopicService';
import type { ClientInfo, LifecycleStatus, MasterAudience, MasterCategory, MasterDifficulty, MasterOptics,
  MasterQuestion, MasterScenarioFull, MasterScenarioInput, MasterTopicFull, MasterTopicInput } from '../../types/api';

type QuestionDraft = { id?: string; text: string };
type TopicDraft = Omit<MasterTopicInput, 'questions'> & { questions: QuestionDraft[] };
const newTopic = (): TopicDraft => ({ name: '', context: '', optics: 'empathetic', audience: 'leadership', keyMessages: [], redLines: [], questions: [] });
const topicDraft = (topic: MasterTopicFull): TopicDraft => ({ name: topic.name, context: topic.context, optics: topic.optics, audience: topic.audience,
  keyMessages: topic.keyMessages, redLines: topic.redLines, questions: topic.questions.map(q => ({ id: q.id, text: q.text })) });

interface Props { topicId: string | null; onBack: () => void; onCreated: (id: string) => void }

export function MasterTopicEditorView({ topicId, onBack, onCreated }: Props) {
  const { t } = useI18n(); const d = t.masterTopics;
  const [topic, setTopic] = useState<MasterTopicFull | null>(null);
  const [draft, setDraft] = useState<TopicDraft>(newTopic);
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [pendingText, setPendingText] = useState({ keyMessages: '', redLines: '', questions: '' });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [scenarioEdit, setScenarioEdit] = useState<MasterScenarioFull | 'new' | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([service.clients(), topicId ? service.topic(topicId) : Promise.resolve(null)])
      .then(([clientItems, full]) => { if (active) { setClients(clientItems); setTopic(full); setDraft(full ? topicDraft(full) : newTopic()); } })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : d.error); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [topicId, d.error]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(topic ? topicDraft(topic) : newTopic()) || Object.values(pendingText).some(text => text.trim());
  const patch = <K extends keyof TopicDraft>(key: K, value: TopicDraft[K]) => { setDraft(old => ({ ...old, [key]: value })); setNotice(''); };
  const saveTopic = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim() || !draft.context.trim() || Object.values(pendingText).some(text => text.trim())) { setError(d.requiredTopic); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      const full = await service.saveTopic(draft, topic?.id);
      setTopic(full); setDraft(topicDraft(full)); setNotice(d.saved);
      if (!topicId) onCreated(full.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : d.error); }
    finally { setBusy(false); }
  };

  const scenarioStatus = async (scenario: MasterScenarioFull, status: LifecycleStatus) => {
    if (!topic) return;
    setBusy(true); setError('');
    try { await service.scenarioStatus(scenario.id, status); setTopic(await service.topic(topic.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : d.error); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="canvas-content" role="status">{d.loading}</div>;
  if (topicId && !topic) return <div className="canvas-content"><p role="alert">{error}</p><button type="button" className="btn" onClick={onBack}>{d.back}</button></div>;

  return <div className="canvas-content">
    <div className="master-heading"><h2>{d.editor}</h2><button type="button" className="btn ghost" disabled={busy} onClick={onBack}>{d.back}</button></div>
    {error && <p role="alert" className="master-error">{error}</p>}
    {notice && <p role="status" style={{ color: 'var(--accent)' }}>{notice}</p>}
    <form onSubmit={event => void saveTopic(event)}>
      <fieldset className="master-fieldset" disabled={busy || scenarioEdit !== null}>
        <div className="card">
          <label className="label" htmlFor="topic-name">{d.name} *</label><input id="topic-name" className="field" required maxLength={150} value={draft.name} onChange={e => patch('name', e.target.value)} />
          <label className="label" htmlFor="topic-context">{d.context} *</label><textarea id="topic-context" className="field" required rows={4} value={draft.context} onChange={e => patch('context', e.target.value)} />
          <div className="grid2">
            <div><div className="label">{d.optics}</div><div className="master-pills">{(Object.keys(labels.optics) as MasterOptics[]).map(value => <button type="button" className={`pill ${draft.optics === value ? 'on' : ''}`} aria-pressed={draft.optics === value} key={value} onClick={() => patch('optics', value)}>{labels.optics[value]}</button>)}</div></div>
            <div><div className="label">{d.audience}</div><div className="master-pills">{(Object.keys(labels.audience) as MasterAudience[]).map(value => <button type="button" className={`pill ${draft.audience === value ? 'on' : ''}`} aria-pressed={draft.audience === value} key={value} onClick={() => patch('audience', value)}>{labels.audience[value]}</button>)}</div></div>
          </div>
        </div>
        <div className="grid2" style={{ marginTop: 16 }}>
          {(['keyMessages', 'redLines'] as const).map(field => <TextList key={field} label={d[field]} warning={field === 'redLines'} entries={draft[field].map(text => ({ text }))}
            pending={pendingText[field]} onPending={text => setPendingText(old => ({ ...old, [field]: text }))}
            onAdd={() => { if (pendingText[field].trim()) { patch(field, [...draft[field], pendingText[field].trim()]); setPendingText(old => ({ ...old, [field]: '' })); } }}
            onChange={(index, text) => patch(field, draft[field].map((old, i) => i === index ? text : old))}
            onRemove={index => patch(field, draft[field].filter((_, i) => i !== index))} />)}
        </div>
        <div style={{ marginTop: 16 }}><TextList label={d.bank} entries={draft.questions} pending={pendingText.questions}
          onPending={text => setPendingText(old => ({ ...old, questions: text }))}
          onAdd={() => { if (pendingText.questions.trim()) { patch('questions', [...draft.questions, { text: pendingText.questions.trim() }]); setPendingText(old => ({ ...old, questions: '' })); } }}
          onChange={(index, text) => patch('questions', draft.questions.map((q, i) => i === index ? { ...q, text } : q))}
          onRemove={index => patch('questions', draft.questions.filter((_, i) => i !== index))} questions />
        </div>
        <button className="btn pri" type="submit" style={{ margin: '18px 0' }}>{busy ? d.saving : d.saveTopic}</button>
      </fieldset>
    </form>
    <section className="card" aria-labelledby="scenario-section-title">
      <div className="master-heading"><h3 id="scenario-section-title">{d.scenarios}</h3>
        <button type="button" className="btn pri" disabled={!topic || topic.status !== 'active' || !!dirty || busy || scenarioEdit !== null} onClick={() => { setError(''); setScenarioEdit('new'); }}>{d.newScenario}</button></div>
      {!topic ? <p>{d.saveFirst}</p> : <>
        {topic.status === 'archived' ? <p>{d.archivedTopic}</p> : dirty ? <p role="status">{d.unsaved}</p> : null}
        {topic.scenarios.length === 0 && <p>{d.noScenarios}</p>}
        {topic.scenarios.map(scenario => <div className="master-question" key={scenario.id}>
          <div style={{ flex: 1 }}><strong>{scenario.title}</strong><div className="master-pills" style={{ marginTop: 8 }}>
            {[labels.category[scenario.category], labels.difficulty[scenario.difficulty], `${scenario.estimatedMinutes} min`, scenario.clientName, labels.status[scenario.status], `${scenario.questionCount} ${d.questionsCount}`].map((label, index) => <span className="tagm" key={index}>{label}</span>)}</div></div>
          <button type="button" className="btn ghost" disabled={busy || !!dirty || scenarioEdit !== null || topic.status !== 'active'} onClick={() => { setError(''); setScenarioEdit(scenario); }}>✏️ {d.edit}</button>
          <button type="button" className="btn ghost" disabled={busy || !!dirty || scenarioEdit !== null || (scenario.status === 'archived' && topic.status !== 'active')} onClick={() => void scenarioStatus(scenario, scenario.status === 'active' ? 'archived' : 'active')}>{scenario.status === 'active' ? d.archive : d.reactivate}</button>
        </div>)}
        {scenarioEdit && <ScenarioEditor key={scenarioEdit === 'new' ? 'new' : scenarioEdit.id} topic={topic} clients={clients} existing={scenarioEdit === 'new' ? undefined : scenarioEdit}
          onCancel={() => setScenarioEdit(null)} onSaved={full => { setTopic(full); setDraft(topicDraft(full)); setScenarioEdit(null); }} />}
      </>}
    </section>
  </div>;
}

function TextList(props: { label: string; entries: QuestionDraft[]; pending: string; questions?: boolean; warning?: boolean;
  onPending: (text: string) => void; onAdd: () => void; onChange: (index: number, text: string) => void; onRemove: (index: number) => void }) {
  const { t } = useI18n(); const d = t.masterTopics;
  return <div className={`card ${props.warning ? 'master-warning' : ''}`}>
    <h3>{props.warning && '🚫 '}{props.label} ({props.entries.length})</h3>
    {props.entries.map((entry, index) => <div className="master-question" key={entry.id || index}>
      <span className="tagm">#{index + 1}</span><textarea className="field" rows={2} required maxLength={500} aria-label={`${props.label} ${index + 1}`} value={entry.text} onChange={e => props.onChange(index, e.target.value)} />
      <button type="button" className="btn ghost" aria-label={`${d.remove} ${props.label} ${index + 1}`} onClick={() => props.onRemove(index)}>✕</button>
    </div>)}
    <div className="master-question"><input className="field" maxLength={500} aria-label={`${d.add} ${props.label}`} value={props.pending} onChange={e => props.onPending(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); props.onAdd(); } }} />
      <button type="button" className="btn" disabled={!props.pending.trim()} onClick={props.onAdd}>{props.questions ? d.addQuestion : `+ ${d.add}`}</button></div>
  </div>;
}

function ScenarioEditor({ topic, clients, existing, onCancel, onSaved }: { topic: MasterTopicFull; clients: ClientInfo[]; existing?: MasterScenarioFull; onCancel: () => void; onSaved: (topic: MasterTopicFull) => void }) {
  const { t } = useI18n(); const d = t.masterTopics;
  const [title, setTitle] = useState(existing?.title || '');
  const [category, setCategory] = useState<MasterCategory | ''>(existing?.category || '');
  const [difficulty, setDifficulty] = useState<MasterDifficulty | ''>(existing?.difficulty || '');
  const [minutes, setMinutes] = useState(existing ? String(existing.estimatedMinutes) : '');
  const [clientId, setClientId] = useState(existing?.clientId || '');
  const [selected, setSelected] = useState<string[]>(existing?.questionIds || []);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const questionMap = new Map<string, MasterQuestion>([...(existing?.questions || []), ...topic.questions].map(q => [q.id, q]));
  const move = (index: number, delta: number) => {
    const reordered = [...selected];
    [reordered[index], reordered[index + delta]] = [reordered[index + delta], reordered[index]];
    setSelected(reordered);
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !category || !difficulty || !Number.isInteger(Number(minutes)) || Number(minutes) <= 0 || !clientId || !selected.length) { setError(d.requiredScenario); return; }
    const payload: MasterScenarioInput = { title: title.trim(), category, difficulty, estimatedMinutes: Number(minutes), clientId, questionIds: selected };
    setBusy(true); setError('');
    try { await service.saveScenario(topic.id, payload, existing?.id); onSaved(await service.topic(topic.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : d.error); }
    finally { setBusy(false); }
  };
  return <form className="master-scenario-editor" onSubmit={event => void save(event)} aria-label={d.editor}>
    <fieldset className="master-fieldset" disabled={busy}>
      <h3>{existing ? `${d.edit}: ${existing.title}` : d.newScenario}</h3>
      {error && <p role="alert" className="master-error">{error}</p>}
      <label className="label" htmlFor="scenario-title">{d.title} *</label><input id="scenario-title" className="field" required maxLength={150} value={title} onChange={e => setTitle(e.target.value)} />
      <div className="grid2">
        <div><div className="label">{d.category} *</div><div className="master-pills">{(Object.keys(labels.category) as MasterCategory[]).map(value => <button type="button" className={`pill ${category === value ? 'on' : ''}`} aria-pressed={category === value} key={value} onClick={() => setCategory(value)}>{labels.category[value]}</button>)}</div></div>
        <div><div className="label">{d.difficulty} *</div><div className="master-pills">{(Object.keys(labels.difficulty) as MasterDifficulty[]).map(value => <button type="button" className={`pill ${difficulty === value ? 'on' : ''}`} aria-pressed={difficulty === value} key={value} onClick={() => setDifficulty(value)}>{labels.difficulty[value]}</button>)}</div></div>
      </div>
      <div className="grid2" style={{ margin: '16px 0' }}>
        <div><label className="label" htmlFor="scenario-minutes">{d.duration} *</label><input id="scenario-minutes" className="field" type="number" required min={1} step={1} value={minutes} onChange={e => setMinutes(e.target.value)} /></div>
        <div><label className="label" htmlFor="scenario-client">{d.client} *</label><select id="scenario-client" className="field" required value={clientId} onChange={e => setClientId(e.target.value)}><option value="">{d.chooseClient}</option>{clients.map(client => <option value={client.id} key={client.id}>{client.name}</option>)}
          {existing && !clients.some(c => c.id === existing.clientId) && <option disabled value={existing.clientId}>{existing.clientName} ({d.archived})</option>}</select></div>
      </div>
      <div className="grid2">
        <div className="card"><h4>{d.bank} ({topic.questions.length})</h4>
          {topic.questions.map((question, index) => <div className="master-question" key={question.id}><span>#{index + 1} {question.text}</span><button type="button" className="btn" disabled={selected.includes(question.id)} onClick={() => setSelected(old => [...old, question.id])}>+ {d.add}</button></div>)}
        </div>
        <div className="card"><h4>{d.selectedQuestions} ({selected.length}) *</h4><ol className="master-selected">
          {selected.map((questionId, index) => <li className="master-question" key={questionId}>
            <div style={{ flex: 1 }}><strong>#{index + 1}</strong> {questionMap.get(questionId)?.text}
              {questionMap.get(questionId)?.status === 'archived' && <span className="tagm">{d.archivedQuestion}</span>}</div>
            <div className="master-pills"><button type="button" className="btn ghost" aria-label={`${d.up} ${index + 1}`} disabled={index === 0} onClick={() => move(index, -1)}>▲</button>
              <button type="button" className="btn ghost" aria-label={`${d.down} ${index + 1}`} disabled={index === selected.length - 1} onClick={() => move(index, 1)}>▼</button>
              <button type="button" className="btn ghost" aria-label={`${d.remove} ${index + 1}`} onClick={() => setSelected(old => old.filter(id => id !== questionId))}>✕</button></div>
          </li>)}
        </ol></div>
      </div>
      <div className="master-pills" style={{ marginTop: 16 }}><button type="submit" className="btn pri">{busy ? d.saving : d.saveScenario}</button><button type="button" className="btn ghost" onClick={onCancel}>{d.cancel}</button></div>
    </fieldset>
  </form>;
}
