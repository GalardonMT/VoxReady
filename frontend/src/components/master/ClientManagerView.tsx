'use client';

import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import type { ClientInfo, ClientStatus, SpokespersonCandidate } from '../../types/api';
import { ApiError } from '../../services/apiClient';
import { clientService } from '../../services/clientService';
import { normalizeClient, validateClient } from '../../services/clientRules';

const statusLabels: Record<ClientStatus, string> = { active: 'Activo', suspended: 'Suspendido' };

function errorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.problem.status === 403) {
    return 'Tu usuario no tiene permisos para administrar clientes ni voceros.';
  }
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

interface SelectorProps {
  candidates: SpokespersonCandidate[];
  selected: string[];
  search: string;
  loading: boolean;
  error: string;
  disabled: boolean;
  searchId: string;
  onSearch: (value: string) => void;
  onToggle: (candidate: SpokespersonCandidate) => void;
  onRetry: () => void;
}

const SpokespersonSelector: React.FC<SelectorProps> = ({
  candidates, selected, search, loading, error, disabled, searchId, onSearch, onToggle, onRetry,
}) => {
  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase('es');
    if (!term) return candidates;
    return candidates.filter(candidate =>
      candidate.displayName.toLocaleLowerCase('es').includes(term)
      || candidate.email.toLocaleLowerCase('es').includes(term));
  }, [candidates, search]);
  const availableCount = candidates.filter(candidate => candidate.linkState === 'available').length;

  return <div className="spokesperson-selector">
    <label htmlFor={searchId}>Buscar vocero por nombre o correo
      <input id={searchId} className="field" type="search" value={search} disabled={disabled || loading}
        onChange={event => onSearch(event.target.value)} placeholder="Nombre o correo" />
    </label>
    {loading ? <p role="status">Cargando voceros…</p> : error ? <div className="master-error" role="alert">
      <p>{error}</p><button type="button" className="btn ghost" disabled={disabled} onClick={onRetry}>Reintentar</button>
    </div> : candidates.length === 0 ? <p className="spokesperson-empty">No hay voceros existentes para seleccionar.</p> : <>
      {availableCount === 0 && <p className="spokesperson-empty" role="status">
        No hay voceros disponibles: todos los voceros existentes ya pertenecen a una empresa.
      </p>}
      <div className="spokesperson-options" aria-label="Voceros existentes">
        {filtered.length === 0 ? <p className="spokesperson-empty">No hay coincidencias para la búsqueda.</p> : filtered.map(candidate => {
          const linked = candidate.linkState === 'linked';
          const unavailable = candidate.linkState === 'assigned_elsewhere';
          const checked = linked || selected.includes(candidate.id);
          const explanation = linked
            ? 'Vinculado a esta empresa. La desvinculación no está disponible.'
            : unavailable
              ? `Pertenece a ${candidate.clientName || 'otra empresa'}; no se puede trasladar.`
              : 'Disponible para vincular.';
          return <label className={`spokesperson-option ${unavailable ? 'unavailable' : ''}`} key={candidate.id}>
            <input type="checkbox" checked={checked} disabled={disabled || linked || unavailable}
              onChange={() => onToggle(candidate)} />
            <span><strong>{candidate.displayName}</strong><span>{candidate.email}</span><small>{explanation}</small></span>
          </label>;
        })}
      </div>
    </>}
  </div>;
};

export const ClientManagerView: React.FC = () => {
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [status, setStatus] = useState<ClientStatus>('active');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');
  const [formCandidates, setFormCandidates] = useState<SpokespersonCandidate[]>([]);
  const [formCandidatesLoading, setFormCandidatesLoading] = useState(false);
  const [formCandidatesError, setFormCandidatesError] = useState('');
  const [formSearch, setFormSearch] = useState('');
  const [formSpokespersonIds, setFormSpokespersonIds] = useState<string[]>([]);
  const [managedClient, setManagedClient] = useState<ClientInfo | null>(null);
  const [manageCandidates, setManageCandidates] = useState<SpokespersonCandidate[]>([]);
  const [manageCandidatesLoading, setManageCandidatesLoading] = useState(false);
  const [manageCandidatesError, setManageCandidatesError] = useState('');
  const [manageSearch, setManageSearch] = useState('');
  const [manageSpokespersonIds, setManageSpokespersonIds] = useState<string[]>([]);
  const [manageSaving, setManageSaving] = useState(false);
  const [manageError, setManageError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setLoadError('');
    try { setClients(await clientService.list()); }
    catch (cause) { setLoadError(errorMessage(cause, 'No se pudo cargar la lista de clientes.')); }
    finally { setLoading(false); }
  }, []);

  const loadFormCandidates = useCallback(async () => {
    setFormCandidatesLoading(true); setFormCandidatesError('');
    try { setFormCandidates(await clientService.spokespersons()); }
    catch (cause) { setFormCandidatesError(errorMessage(cause, 'No se pudieron cargar los voceros.')); }
    finally { setFormCandidatesLoading(false); }
  }, []);

  const loadManageCandidates = useCallback(async (client: ClientInfo) => {
    setManageCandidatesLoading(true); setManageCandidatesError('');
    try {
      const items = await clientService.spokespersons(client.id);
      setManageCandidates(items);
      setManageSpokespersonIds(items.filter(item => item.linkState === 'linked').map(item => item.id));
    } catch (cause) {
      setManageCandidatesError(errorMessage(cause, 'No se pudieron cargar los voceros del cliente.'));
    } finally { setManageCandidatesLoading(false); }
  }, []);

  useEffect(() => {
    let active = true;
    clientService.list()
      .then(items => { if (active) setClients(items); })
      .catch(cause => {
        if (active) setLoadError(errorMessage(cause, 'No se pudo cargar la lista de clientes.'));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const toggle = (candidate: SpokespersonCandidate, setter: React.Dispatch<React.SetStateAction<string[]>>) => {
    if (candidate.linkState !== 'available') return;
    setter(current => current.includes(candidate.id) ? current.filter(id => id !== candidate.id) : [...current, candidate.id]);
  };

  const openCreate = () => {
    setShowForm(true); setManagedClient(null); setFormError(''); setNotice('');
    void loadFormCandidates();
  };

  const cancel = () => {
    setShowForm(false); setName(''); setStatus('active'); setFormError(''); setFormSearch(''); setFormSpokespersonIds([]);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validateClient(name, status);
    if (validation) { setFormError(validation); return; }
    setSaving(true); setFormError(''); setNotice('');
    try {
      const saved = await clientService.create(normalizeClient(name, status, formSpokespersonIds));
      setClients(current => [...current, saved].sort((a, b) => a.name.localeCompare(b.name, 'es', { sensitivity: 'base' })));
      setNotice(`Cliente “${saved.name}” registrado correctamente${formSpokespersonIds.length ? ' con sus voceros' : ''}.`);
      cancel();
    } catch (cause) {
      setFormError(errorMessage(cause, 'No se pudo registrar el cliente. Inténtalo nuevamente.'));
    } finally { setSaving(false); }
  };

  const openManagement = (client: ClientInfo) => {
    setShowForm(false); setManagedClient(client); setManageSearch(''); setManageError(''); setNotice('');
    void loadManageCandidates(client);
  };

  const saveManagement = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!managedClient) return;
    setManageSaving(true); setManageError(''); setNotice('');
    try {
      await clientService.linkSpokespersons(managedClient.id, manageSpokespersonIds);
      await loadManageCandidates(managedClient);
      setNotice(`Voceros de “${managedClient.name}” actualizados correctamente.`);
    } catch (cause) {
      setManageError(errorMessage(cause, 'No se pudieron vincular los voceros.'));
    } finally { setManageSaving(false); }
  };

  return <div className="canvas-content">
    <div className="master-heading"><div><h2>Clientes</h2><p className="legend">Empresas registradas en VoxReady.</p></div>
      <button type="button" className="btn pri" disabled={showForm || saving} onClick={openCreate}>＋ Nuevo cliente</button></div>
    {notice && <p className="master-success" role="status" aria-live="polite">{notice}</p>}

    {showForm && <form className="card client-editor" onSubmit={save} noValidate>
      <div className="master-heading"><h3>Registrar cliente</h3></div>
      {formError && <p className="master-error" role="alert">{formError}</p>}
      <fieldset className="master-fieldset" disabled={saving}>
        <div className="client-form-grid">
          <label htmlFor="client-name">Nombre de la empresa *
            <input id="client-name" name="name" className="field" type="text" required maxLength={150} autoComplete="organization" autoFocus value={name} onChange={event => setName(event.target.value)} />
          </label>
          <label htmlFor="client-status">Estado *
            <select id="client-status" name="status" className="field" value={status} onChange={event => setStatus(event.target.value as ClientStatus)}>
              <option value="active">Activo</option><option value="suspended">Suspendido</option>
            </select>
          </label>
        </div>
        <div className="client-spokespersons"><h4>Voceros (opcional)</h4>
          <p className="legend">Selecciona usuarios existentes sin empresa. No se crearán cuentas nuevas.</p>
          <SpokespersonSelector candidates={formCandidates} selected={formSpokespersonIds} search={formSearch} loading={formCandidatesLoading} error={formCandidatesError} disabled={saving} searchId="create-spokesperson-search" onSearch={setFormSearch} onToggle={candidate => toggle(candidate, setFormSpokespersonIds)} onRetry={() => void loadFormCandidates()} />
        </div>
        <div className="master-actions client-form-actions"><button type="button" className="btn" onClick={cancel}>Cancelar</button>
          <button type="submit" className="btn pri" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button></div>
      </fieldset>
    </form>}

    {managedClient && <form className="card client-editor" onSubmit={saveManagement}>
      <div className="master-heading"><div><h3>Gestionar voceros</h3><p className="legend">{managedClient.name}</p></div>
        <button type="button" className="btn ghost" disabled={manageSaving} onClick={() => setManagedClient(null)}>Cerrar</button></div>
      {manageError && <p className="master-error" role="alert">{manageError}</p>}
      <fieldset className="master-fieldset" disabled={manageSaving}>
        <SpokespersonSelector candidates={manageCandidates} selected={manageSpokespersonIds} search={manageSearch} loading={manageCandidatesLoading} error={manageCandidatesError} disabled={manageSaving} searchId="manage-spokesperson-search" onSearch={setManageSearch} onToggle={candidate => toggle(candidate, setManageSpokespersonIds)} onRetry={() => void loadManageCandidates(managedClient)} />
        <div className="master-actions client-form-actions"><button type="button" className="btn" onClick={() => setManagedClient(null)}>Cancelar</button>
          <button type="submit" className="btn pri" disabled={manageSaving || manageCandidatesLoading}>{manageSaving ? 'Guardando…' : 'Guardar vínculos'}</button></div>
      </fieldset>
    </form>}

    <section className="card" aria-labelledby="client-list-title"><div className="master-heading"><h3 id="client-list-title">Empresas</h3></div>
      {loading ? <p role="status">Cargando clientes…</p> : loadError ? <div className="master-error" role="alert"><p>{loadError}</p><button type="button" className="btn ghost" onClick={() => void load()}>Reintentar</button></div>
        : clients.length === 0 ? <p>No hay clientes registrados.</p> : <div className="master-table-wrap"><table className="master-table">
          <thead><tr><th>Nombre</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{clients.map(client => <tr key={client.id}>
            <td>{client.name}</td><td><span className={`client-status ${client.status ?? 'active'}`}>{statusLabels[client.status ?? 'active']}</span></td>
            <td><button type="button" className="btn ghost" disabled={manageSaving} onClick={() => openManagement(client)}>Gestionar voceros</button></td>
          </tr>)}</tbody></table></div>}
    </section>
  </div>;
};
