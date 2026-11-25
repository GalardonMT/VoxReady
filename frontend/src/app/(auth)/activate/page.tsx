'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useMsal } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { isAzureConfigured, loginRedirectRequest, loginRequest } from '../../../services/authConfig';
import { useAuth } from '../../../context/AuthContext';
import { accessDiagnosticStep } from '../../../services/accessDiagnosticStep';
import { inspectInvitation, checkInvitationIdentity, completeInvitation,
  type InvitationInspection, type IdentityStatus } from '../../../services/pendingAccessService';

function EntraActivation() {
  const { instance, accounts, inProgress } = useMsal();
  const { refreshProfile } = useAuth();
  const [invitation, setInvitation] = useState<InvitationInspection | null>(null);
  const [status, setStatus] = useState<IdentityStatus | null>(null);
  const [message, setMessage] = useState('Comprobando enlace…');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(false);
  const account = instance.getActiveAccount() || accounts[0];
  const canActivate = account && invitation?.activationAvailable && (
    invitation.role === 'client_admin' || invitation.accountChoice || status?.fixedEmailActivationAvailable === true);

  useEffect(() => {
    let active = true;
    inspectInvitation(window.location.hash.slice(1)).then(data => {
      if (active) {
        setInvitation(data);
        setMessage(data.role === 'spokesperson' && !data.accountChoice
          ? 'Ingresa con el correo que registró el configurador maestro para este vocero.'
          : 'Elige tu correo al registrarte o iniciar sesión en Microsoft Entra.');
      }
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'No se pudo comprobar el enlace.'); });
    return () => { active = false; };
  }, []);

  async function authenticate() {
    setError(''); setStatus(null);
    try {
      // MSAL conserva el retorno y valida state/nonce/PKCE. No se envía el secreto
      // al endpoint Entra; permanece en el fragmento del retorno del mismo sitio.
      await instance.loginRedirect({ ...loginRedirectRequest, redirectStartPage: window.location.href });
    } catch { setError('No se pudo abrir Microsoft Entra. Inténtalo nuevamente.'); }
  }

  async function bearer() {
    if (!account) throw new Error('Inicia sesión primero.');
    return (await accessDiagnosticStep(
      () => instance.acquireTokenSilent({ ...loginRequest, account, forceRefresh: true }), 20000,
      'Microsoft Entra no respondió en 20 segundos. Vuelve a seleccionar tu cuenta e inténtalo nuevamente.')).accessToken;
  }

  async function check() {
    setBusy(true); setError(''); setStatus(null);
    try { setStatus(await checkInvitationIdentity(await bearer())); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo comprobar la identidad.'); }
    finally { setBusy(false); }
  }

  async function activate() {
    setBusy(true); setError('');
    try {
      await completeInvitation(window.location.hash.slice(1), await bearer());
      window.history.replaceState(null, '', window.location.pathname);
      setCompleted(true); setInvitation(null); setStatus(null);
      setMessage('Acceso activado. El enlace ya fue utilizado y no puede volver a activar otra cuenta.');
      await refreshProfile();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo confirmar la activación. Consulta su estado antes de intentarlo nuevamente.'); }
    finally { setBusy(false); }
  }

  return <>
    <p role="status">{message}</p>
    {error && <p role="alert">{error}</p>}
    {busy && <p role="status" aria-live="polite">Comprobando la cuenta y el acceso. Espera el resultado…</p>}
    {invitation && <>
      <p>Abrir o comprobar este enlace no lo consume. Tiene una vigencia de 48 horas.</p>
      {!invitation.activationAvailable && <p>La activación está pendiente de verificación por el responsable de VoxReady. Puedes comprobar tu cuenta sin activar el acceso.</p>}
      {(invitation.role === 'client_admin' || invitation.accountChoice) && <p>El enlace autoriza el rol y la empresa. Al activar, se vinculará la cuenta de Entra seleccionada; no se reasignará ningún perfil existente por correo.</p>}
      {account && <p>Cuenta seleccionada: {account.username || 'Microsoft Entra'}. Si no corresponde, cambia de cuenta.</p>}
      <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void authenticate()}>
        {account ? 'Cambiar cuenta de Microsoft Entra' : 'Registrarme o ingresar con Microsoft Entra'}</button>
      {account && <button type="button" className="btn" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void check()}>Comprobar cuenta</button>}
      {canActivate && <button type="button" className="btn pri" disabled={busy || inProgress !== InteractionStatus.None} onClick={() => void activate()}>Activar acceso</button>}
      {status && <>
        <p>Identidad y permiso de API comprobados. {(invitation.role === 'client_admin'
          ? status.clientAdminActivationAvailable : invitation.accountChoice ? status.spokespersonActivationAvailable : status.fixedEmailActivationAvailable)
          ? 'Puedes completar la activación.' : 'Falta una condición para este tipo de acceso. No se ha activado ni consumido el enlace.'}</p>
        <details><summary>Resultado técnico sin datos personales</summary><pre>{JSON.stringify(status, null, 2)}</pre></details>
      </>}
    </>}
    <Link href="/login">{completed ? 'Ingresar a VoxReady' : 'Volver al ingreso'}</Link>
  </>;
}

export default function ActivatePage() {
  return <main className="login-view"><section className="login-card"><h1>Activar acceso a VoxReady</h1>
    {isAzureConfigured ? <EntraActivation /> : <p role="alert">Microsoft Entra no está configurado. Contacta al responsable de VoxReady.</p>}
  </section></main>;
}
