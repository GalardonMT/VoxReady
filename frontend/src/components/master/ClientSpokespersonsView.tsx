'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { ClientInfo, ClientSpokesperson } from '../../types/api';
import type { ProgressResponse } from '../../services/progressService';
import { clientService } from '../../services/clientService';
import { useI18n } from '../../context/I18nContext';
import { ProgressSummary } from '../spokesperson/ProgressView';

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

function SpokespersonDetail({ clientId, spokesperson }: {
  clientId: string;
  spokesperson: ClientSpokesperson;
}) {
  const { t } = useI18n();
  const d = t.clientSpokespersons;
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestId.current;
    setLoading(true);
    setProgress(null);
    setError('');
    try {
      const result = await clientService.spokespersonProgress(clientId, spokesperson.id);
      if (request === requestId.current) setProgress(result);
    } catch (cause) {
      if (request === requestId.current) setError(errorMessage(cause, d.progressError));
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }, [clientId, spokesperson.id, d.progressError]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; requestId.current += 1; };
  }, [load]);

  const displayName = spokesperson.displayName || spokesperson.email;

  return <section aria-labelledby="client-spokesperson-detail-title">
    <div className="master-heading"><div>
      <h3 id="client-spokesperson-detail-title">{d.detail} {displayName}</h3>
      <p className="legend">{spokesperson.email}</p>
    </div></div>
    {loading ? <div className="card" role="status">{d.loadingProgress}</div>
      : error ? <div className="card master-error" role="alert"><p>{error}</p><button type="button" className="btn ghost" onClick={() => void load()}>{d.retry}</button></div>
        : progress && <>
          <div className="card stat" style={{ marginBottom: '18px' }}>
            <div className="k">{d.completedSessions}</div>
            <div className="v">{progress.sessionsCount}</div>
          </div>
          <ProgressSummary progress={progress} loading={false} error="" onRetry={load} emptyMessage={d.emptyProgress} heading={d.progressHeading} />
        </>}
  </section>;
}

export const ClientSpokespersonsView: React.FC<{
  client: ClientInfo;
  onBack: () => void;
}> = ({ client, onBack }) => {
  const { t } = useI18n();
  const d = t.clientSpokespersons;
  const [spokespersons, setSpokespersons] = useState<ClientSpokesperson[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const request = ++requestId.current;
    setLoading(true);
    setSpokespersons([]);
    setSelectedId(null);
    setError('');
    try {
      const items = await clientService.clientSpokespersons(client.id);
      if (request === requestId.current) setSpokespersons(items);
    } catch (cause) {
      if (request === requestId.current) setError(errorMessage(cause, d.listError));
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }, [client.id, d.listError]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; requestId.current += 1; };
  }, [load]);

  const selected = spokespersons.find(person => person.id === selectedId);

  return <div className="canvas-content">
    <div className="master-heading"><div>
      <nav aria-label={d.clientNavigation} className="master-actions">
        <button type="button" className="btn ghost" onClick={onBack}>← {d.back}</button>
        <span className="legend">{client.name} › {d.view}</span>
      </nav>
      <h2 style={{ marginTop: '12px' }}>{d.title} {client.name}</h2>
    </div></div>
    <section className="card" aria-labelledby="client-spokesperson-list-title">
      <div className="master-heading"><h3 id="client-spokesperson-list-title">{d.list}</h3></div>
      {loading ? <p role="status">{d.loadingList}</p>
        : error ? <div className="master-error" role="alert"><p>{error}</p><button type="button" className="btn ghost" onClick={() => void load()}>{d.retry}</button></div>
          : spokespersons.length === 0 ? <p className="spokesperson-empty">{d.emptyList}</p>
            : <div className="master-table-wrap"><table className="master-table">
              <thead><tr><th>{d.name}</th><th>{d.email}</th><th>{d.action}</th></tr></thead>
              <tbody>{spokespersons.map(person => <tr key={person.id}>
                <td>{person.displayName || person.email}</td><td>{person.email}</td>
                <td><button type="button" className="btn ghost" aria-pressed={person.id === selectedId} onClick={() => setSelectedId(person.id)}>{d.viewProgress}</button></td>
              </tr>)}</tbody>
            </table></div>}
    </section>
    {!loading && !error && spokespersons.length > 0 && (
      selected ? <SpokespersonDetail key={selected.id} clientId={client.id} spokesperson={selected} />
        : <p className="legend" role="status">{d.select}</p>
    )}
  </div>;
};
