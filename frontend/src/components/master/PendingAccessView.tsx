'use client';

import React, { useEffect, useState } from 'react';
import type { ClientInfo } from '../../types/api';
import { pendingAccessService, type PendingAccess, type PendingRole } from '../../services/pendingAccessService';

const states = { pending: 'Sin enlace', invited: 'Enlace vigente', expired: 'Enlace vencido', activated: 'Activado' };

export function PendingAccessView({ client, onBack }: { client: ClientInfo; onBack: () => void }) {
  const [items, setItems] = useState<PendingAccess[]>([]);
  const [role, setRole] = useState<PendingRole>('client_admin');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(true);
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState('');
  const [link, setLink] = useState('');
  const [notice, setNotice] = useState('');
  const [activationByRole, setActivationByRole] = useState<Record<PendingRole, boolean> | null>(null);
  const activationAvailable = activationByRole?.[role] === true;

  useEffect(() => {
    let active = true;
    pendingAccessService.list(client.id).then(data => {
      if (active) { setItems(data.items); setAvailable(true); setActivationByRole(data.activationByRole); }
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudieron cargar los accesos.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [client.id]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setLink(''); setNotice('');
    try {
      const access = await pendingAccessService.create(client.id, {
        role, displayName: name.trim(),
      });
      setItems(current => [...current, access]); setName('');
      setNotice('Acceso pendiente creado. Todavía no permite ingresar a VoxReady.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo crear el acceso.'); }
    finally { setBusy(false); }
  }

  async function generate(item: PendingAccess) {
    const convert = item.role === 'spokesperson' && !item.accountChoice;
    if (convert && !window.confirm('El vocero podrá elegir su cuenta de Entra con el nuevo enlace. El enlace anterior quedará invalidado y el correo anterior se conservará como referencia. ¿Continuar?')) return;
    setBusy(true); setError(''); setLink(''); setNotice('');
    try {
      const result = await pendingAccessService.invitation(client.id, item.id, convert);
      setLink(new URL(result.activationPath, window.location.origin).href);
      setItems(current => current.map(row => row.id === item.id ? { ...row, expiresAt: result.expiresAt,
        accountChoice: result.accountChoice, state: 'invited' } : row));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo generar el enlace.'); }
    finally { setBusy(false); }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(link); setNotice('Enlace copiado.'); }
    catch { setError('No se pudo copiar. Selecciona el enlace y cópialo manualmente.'); }
  }

  return <div className="canvas-content">
    <div className="master-heading"><div><h2>Accesos pendientes</h2><p>{client.name}</p></div>
      <button type="button" className="btn" disabled={busy} onClick={onBack}>Volver a clientes</button></div>
    <p className="legend" role="status">{activationAvailable
      ? 'Los enlaces permiten activar el acceso mediante Microsoft Entra y vencen a las 48 horas.'
      : 'La activación con Microsoft Entra está pendiente de validación. Los enlaces pueden prepararse, pero todavía no completan el registro.'}</p>
    {error && <p className="master-error" role="alert">{error}</p>}
    {notice && <p className="master-success" role="status">{notice}</p>}
    {busy && <p role="status">Procesando…</p>}
    <form className="card client-editor" onSubmit={event => void create(event)}>
      <fieldset className="master-fieldset" disabled={busy || !available}>
        <legend>Crear acceso pendiente</legend>
        <label>Tipo de acceso<select className="field" value={role} onChange={event => setRole(event.target.value as PendingRole)}>
          <option value="client_admin">Administrador cliente</option><option value="spokesperson">Vocero</option>
        </select></label>
        <label>Nombre<input className="field" required maxLength={150} value={name} onChange={event => setName(event.target.value)} /></label>
        <p>{role === 'spokesperson' ? 'El vocero elegirá su correo al activar mediante Microsoft Entra.'
          : 'El administrador elegirá su correo al activar mediante Microsoft Entra.'}</p>
        <button type="submit" className="btn pri">Crear acceso pendiente</button>
      </fieldset>
    </form>
    {link && <section className="card"><label>Enlace de activación (48 horas)
      <input className="field" readOnly value={link} onFocus={event => event.currentTarget.select()} /></label>
      <button type="button" className="btn" onClick={() => void copy()}>Copiar enlace</button>
      <p>Guárdalo antes de cerrar esta vista. Si generas otro, este enlace quedará invalidado.</p></section>}
    <section className="card"><h3>Accesos de esta empresa</h3>
      {available && !items.length && <p>No hay accesos pendientes.</p>}
      <div className="master-table-wrap"><table className="master-table"><thead><tr><th>Nombre</th><th>Rol</th><th>Correo</th><th>Estado</th><th>Vence</th><th>Enlace</th></tr></thead>
        <tbody>{items.map(item => <tr key={item.id}><td>{item.displayName}</td><td>{item.role === 'client_admin' ? 'Administrador cliente' : 'Vocero'}</td>
          <td>{item.accountChoice ? <>Se elige al activar{item.email && <small> · Correo anterior conservado como referencia</small>}</>
            : item.email || 'Se elige al activar'}</td><td>{states[item.state]}</td>
          <td>{item.expiresAt ? new Date(item.expiresAt).toLocaleString() : '—'}</td>
          <td><button type="button" className="btn ghost" disabled={busy || item.state === 'activated'} onClick={() => void generate(item)}>
            {item.role === 'spokesperson' && !item.accountChoice ? 'Generar enlace con cuenta a elección'
              : item.expiresAt ? 'Reemplazar enlace' : 'Generar enlace'}</button></td></tr>)}</tbody></table></div>
    </section>
  </div>;
}
