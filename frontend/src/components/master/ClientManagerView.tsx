'use client';

import React, { FormEvent, useCallback, useEffect, useState } from 'react';
import type { ClientInfo, ClientStatus } from '../../types/api';
import { ApiError } from '../../services/apiClient';
import { clientService } from '../../services/clientService';
import { normalizeClient, validateClient } from '../../services/clientRules';

const statusLabels: Record<ClientStatus, string> = {
  active: 'Activo',
  suspended: 'Suspendido',
};

function errorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.problem.status === 403) {
    return 'Tu usuario no tiene permisos para administrar clientes.';
  }
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

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

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      setClients(await clientService.list());
    } catch (cause) {
      setLoadError(errorMessage(cause, 'No se pudo cargar la lista de clientes.'));
    } finally {
      setLoading(false);
    }
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

  const cancel = () => {
    setShowForm(false);
    setName('');
    setStatus('active');
    setFormError('');
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validateClient(name, status);
    if (validation) {
      setFormError(validation);
      return;
    }

    setSaving(true);
    setFormError('');
    setNotice('');
    try {
      const saved = await clientService.create(normalizeClient(name, status));
      setClients(current => [...current, saved].sort((a, b) =>
        a.name.localeCompare(b.name, 'es', { sensitivity: 'base' })));
      setNotice(`Cliente “${saved.name}” registrado correctamente.`);
      setShowForm(false);
      setName('');
      setStatus('active');
    } catch (cause) {
      // El borrador se conserva para que el usuario pueda corregir o reintentar.
      setFormError(errorMessage(cause, 'No se pudo registrar el cliente. Inténtalo nuevamente.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="canvas-content">
      <div className="master-heading">
        <div>
          <h2>Clientes</h2>
          <p className="legend">Empresas registradas en VoxReady.</p>
        </div>
        <button
          type="button"
          className="btn pri"
          disabled={showForm || saving}
          onClick={() => {
            setShowForm(true);
            setFormError('');
            setNotice('');
          }}
        >
          ＋ Nuevo cliente
        </button>
      </div>

      {notice && <p className="master-success" role="status" aria-live="polite">{notice}</p>}

      {showForm && (
        <form className="card client-editor" onSubmit={save} noValidate>
          <div className="master-heading"><h3>Registrar cliente</h3></div>
          {formError && <p className="master-error" role="alert">{formError}</p>}
          <fieldset className="master-fieldset" disabled={saving}>
            <div className="client-form-grid">
              <label htmlFor="client-name">
                Nombre de la empresa *
                <input
                  id="client-name"
                  name="name"
                  className="field"
                  type="text"
                  required
                  maxLength={150}
                  autoComplete="organization"
                  autoFocus
                  value={name}
                  onChange={event => setName(event.target.value)}
                />
              </label>
              <label htmlFor="client-status">
                Estado *
                <select
                  id="client-status"
                  name="status"
                  className="field"
                  value={status}
                  onChange={event => setStatus(event.target.value as ClientStatus)}
                >
                  <option value="active">Activo</option>
                  <option value="suspended">Suspendido</option>
                </select>
              </label>
            </div>
            <div className="master-actions client-form-actions">
              <button type="button" className="btn" onClick={cancel}>Cancelar</button>
              <button type="submit" className="btn pri" disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </fieldset>
        </form>
      )}

      <section className="card" aria-labelledby="client-list-title">
        <div className="master-heading"><h3 id="client-list-title">Empresas</h3></div>
        {loading ? (
          <p role="status">Cargando clientes…</p>
        ) : loadError ? (
          <div className="master-error" role="alert">
            <p>{loadError}</p>
            <button type="button" className="btn ghost" onClick={() => void load()}>Reintentar</button>
          </div>
        ) : clients.length === 0 ? (
          <p>No hay clientes registrados.</p>
        ) : (
          <div className="master-table-wrap">
            <table className="master-table">
              <thead><tr><th>Nombre</th><th>Estado</th></tr></thead>
              <tbody>
                {clients.map(client => (
                  <tr key={client.id}>
                    <td>{client.name}</td>
                    <td>
                      <span className={`client-status ${client.status ?? 'active'}`}>
                        {statusLabels[client.status ?? 'active']}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};
