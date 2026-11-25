'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMsal } from '@azure/msal-react';
import { InteractionRequiredAuthError, InteractionStatus } from '@azure/msal-browser';
import { isAzureConfigured, loginRedirectRequest, loginRequest } from '../../../services/authConfig';
import { checkInvitationIdentity, checkDirectoryIdentity, type IdentityStatus } from '../../../services/pendingAccessService';
import { accessDiagnosticStep } from '../../../services/accessDiagnosticStep';

const graphReadRequest = { scopes: ['https://graph.microsoft.com/User.Read'] };

function CheckIdentity() {
  const { instance, accounts, inProgress } = useMsal();
  const [status, setStatus] = useState<IdentityStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [directory, setDirectory] = useState<Record<string, boolean> | null>(null);
  const [progress, setProgress] = useState('');
  const account = instance.getActiveAccount() || accounts[0];

  async function login() {
    setStatus(null); setDirectory(null); setError('');
    try { await instance.loginRedirect({ ...loginRedirectRequest, redirectStartPage: window.location.href }); }
    catch { setError('No se pudo abrir Microsoft Entra.'); }
  }
  async function check() {
    if (!account) { setError('Selecciona primero una cuenta de Microsoft Entra.'); return; }
    setBusy(true); setStatus(null); setDirectory(null); setError('');
    setProgress('Solicitando un token nuevo de la API a Microsoft Entra…');
    try {
      // Solicita un token nuevo para observar cambios en la emisión de claims;
      // no reutilizar el token anterior guardado antes de cambiar Entra.
      const token = await accessDiagnosticStep(
        () => instance.acquireTokenSilent({ ...loginRequest, account, forceRefresh: true }), 20000,
        'Microsoft Entra no respondió a la solicitud de acceso a la API en 20 segundos. Vuelve a ingresar con tu cuenta.');
      setProgress('Comprobando la identidad recibida por la API…');
      setStatus(await checkInvitationIdentity(token.accessToken));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo comprobar la identidad.'); }
    finally { setBusy(false); setProgress(''); }
  }
  async function checkDirectory() {
    if (!account) { setError('Selecciona primero una cuenta de Microsoft Entra.'); return; }
    setBusy(true); setDirectory(null); setStatus(null); setError('');
    setProgress('Paso 1 de 3: solicitando acceso de lectura a Microsoft Graph (máximo 20 segundos)…');
    try {
      const graphToken = await accessDiagnosticStep(
        () => instance.acquireTokenSilent({ ...graphReadRequest, account, forceRefresh: true }), 20000,
        'Microsoft Entra no respondió a la lectura de Microsoft Graph en 20 segundos. Pulsa «Confirmar lectura de mi perfil» para continuar mediante la pantalla de Entra.');
      setProgress('Paso 2 de 3: solicitando acceso a la API de VoxReady (máximo 20 segundos)…');
      const apiToken = await accessDiagnosticStep(
        () => instance.acquireTokenSilent({ ...loginRequest, account, forceRefresh: true }), 20000,
        'Microsoft Entra no respondió a la solicitud de acceso a la API en 20 segundos. Vuelve a ingresar con tu cuenta.');
      setProgress('Paso 3 de 3: la API está leyendo el perfil propio en Microsoft Graph (máximo 30 segundos)…');
      setDirectory(await checkDirectoryIdentity(apiToken.accessToken, graphToken.accessToken));
    } catch (cause) {
      if (cause instanceof InteractionRequiredAuthError) {
        setError('Microsoft Entra requiere confirmar el permiso de lectura de tu propio perfil. Pulsa «Confirmar lectura de mi perfil».');
      } else setError(cause instanceof Error ? cause.message : 'No se pudo comprobar el directorio.');
    } finally { setBusy(false); setProgress(''); }
  }
  async function authorizeGraphRead() {
    if (!account) { setError('Selecciona primero una cuenta de Microsoft Entra.'); return; }
    setError(''); setStatus(null); setDirectory(null); setBusy(true);
    setProgress('Abriendo Microsoft Entra para confirmar la lectura de tu perfil…');
    try { await accessDiagnosticStep(
      () => instance.acquireTokenRedirect({ ...graphReadRequest, account, redirectStartPage: window.location.href }),
      20000, 'Microsoft Entra no abrió la confirmación en 20 segundos. Recarga la página e inténtalo nuevamente.'); }
    catch { setError('No se pudo solicitar la lectura del perfil en Microsoft Entra.'); }
    finally { setBusy(false); setProgress(''); }
  }
  return <>
    <p>Usa una cuenta Entra existente. Esta comprobación no crea perfiles, empresas ni invitaciones.</p>
    <p>El inicio de sesión puede registrar actividad, una sesión o consentimiento en Entra.</p>
    {error && <p role="alert">{error}</p>}
    {progress && <p role="status" aria-live="polite">{progress}</p>}
    {!busy && inProgress !== InteractionStatus.None && <p role="status">Microsoft Entra está procesando una operación. Los botones estarán disponibles cuando termine.</p>}
    <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void login()}>
      {account ? 'Cambiar cuenta Entra' : 'Ingresar con cuenta Entra existente'}</button>
    {account && <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void check()}>Comprobar identidad recibida por la API</button>}
    {account && <>
      <p>La lectura del directorio consulta solo tu identidad de inicio de sesión y su organización mediante Microsoft Graph. No activa accesos ni cambia perfiles.</p>
      <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void checkDirectory()}>Comprobar correo de inicio de sesión en Entra</button>
      <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void authorizeGraphRead()}>Confirmar lectura de mi perfil</button>
    </>}
    {status && <section><p role="status">Comparte solo este resultado; no contiene correo, identificadores personales ni tokens.</p>
      <pre>{JSON.stringify(status, null, 2)}</pre>
      <p>{status.clientAdminActivationAvailable
        ? 'Puedes activar una invitación de administrador desde su enlace original. Graph no es necesario para ese acceso.'
        : 'Falta una condición para activar invitaciones de administrador.'}</p>
      <p>{status.spokespersonActivationAvailable ? 'Puedes activar una invitación nueva de vocero con la cuenta elegida, sin Microsoft Graph.'
        : 'Falta una condición para activar invitaciones de vocero con elección de cuenta.'}</p>
    </section>}
    {directory && <section><p role="status">Resultado de lectura del directorio sin datos personales:</p>
      <pre>{JSON.stringify(directory, null, 2)}</pre>
      <p>Estos resultados no habilitan por sí solos la activación. Falta acreditar el contrato de verificación del correo.</p>
    </section>}
  </>;
}

export default function AccessCheckPage() {
  return <main className="login-view"><section className="login-card"><h1>Comprobar acceso Entra</h1>
    {isAzureConfigured ? <CheckIdentity /> : <p role="alert">Microsoft Entra no está configurado.</p>}
    <Link href="/login">Volver al ingreso</Link>
  </section></main>;
}
