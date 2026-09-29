'use client';

import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';

export const LoginView: React.FC = () => {
  const { mode, status, error, loginWithEmail, loginExternal, retry } = useAuth();
  const [email, setEmail] = useState('');
  const [localError, setLocalError] = useState('');
  const busy = status === 'loading';

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setLocalError('');
    try { await loginWithEmail(email); }
    catch (cause) { setLocalError(cause instanceof Error ? cause.message : 'No se pudo iniciar sesión.'); }
  };
  return (
    <div className="login-view"><div className="login-card">
      <div className="login-logo"><img src="/VoxReady_logo.png" alt="VoxReady" style={{ height: 42 }} /></div>
      <h1 className="login-title">Iniciar sesión</h1>
      {status === 'expired' && <p className="login-err">Tu sesión caducó. Inicia sesión nuevamente.</p>}
      {status === 'offline' && <p className="login-err">{error} <button type="button" onClick={retry}>Reintentar</button></p>}
      {mode === 'local' && <form onSubmit={submit}>
        <p className="login-sub">Acceso local de desarrollo. Usa el correo de un usuario semilla.</p>
        <div className="login-field"><label htmlFor="dev-email">Correo</label><input id="dev-email" type="email" required className="login-input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
        <button className="login-btn" type="submit" disabled={busy}>Ingresar en desarrollo</button>
      </form>}
      {mode === 'azure' && <button className="login-btn" type="button" disabled={busy} onClick={() => loginExternal().catch((cause) => setLocalError(cause.message))}>Continuar con Microsoft</button>}
      {mode === 'unconfigured' && <p className="login-err">La autenticación no está configurada. Contacta al administrador.</p>}
      {(localError || (status !== 'expired' && status !== 'offline' && error)) && <p className="login-err">{localError || error}</p>}
    </div></div>
  );
};
