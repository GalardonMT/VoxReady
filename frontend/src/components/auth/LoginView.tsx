'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { isAzureConfigured } from '../../services/authConfig';
import { authMode } from '../../services/authService';

interface LoginViewProps {
  onLoginSuccess?: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const { t } = useI18n();
  const { loginWithEmail, loginWithAzure, loading, authError } = useAuth();

  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [azureLoading, setAzureLoading] = useState(false);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError('');
    const success = await loginWithEmail(email);
    if (success) {
      if (onLoginSuccess) onLoginSuccess();
    } else {
      setError(t.login.err);
    }
  };

  const handleAzureLogin = async () => {
    setError('');
    setAzureLoading(true);
    try {
      await loginWithAzure();
      // loginRedirect will navigate away — if we reach here it was a popup or finished
      if (onLoginSuccess) onLoginSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[LoginView] Error logging in with Azure:', msg);
      setError(msg || (t.login.azureErr ?? 'Error al iniciar sesión con Microsoft.'));
    } finally {
      setAzureLoading(false);
    }
  };

  if (loading || azureLoading) {
    return (
      <div className="login-view">
        <div className="login-card">
          <div className="login-logo">
            <div className="brandlogo-wrap">
              <img
                src="/VoxReady_logo.png"
                alt="VoxReady"
                style={{ height: '42px', width: 'auto', display: 'block' }}
              />
            </div>
          </div>
          <p className="login-loading">{t.login.loading ?? 'Autenticando…'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-view">
      <div className="login-card">
        <div className="login-logo">
          <div className="brandlogo-wrap">
            <img
              src="/VoxReady_logo.png"
              alt="VoxReady"
              style={{ height: '42px', width: 'auto', display: 'block' }}
            />
          </div>
        </div>

        <h1 className="login-title">{t.login.title}</h1>
        <p className="login-sub">{t.login.sub}</p>

        {/* ---- Primary: Azure / Microsoft login ---- */}
        {isAzureConfigured && (
          <>
            <button
              type="button"
              className="login-btn login-btn-azure"
              onClick={handleAzureLogin}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 23 23"
                style={{ marginRight: '8px', flexShrink: 0 }}
              >
                <path fill="#f35325" d="M1 1h10v10H1z" />
                <path fill="#81bc06" d="M12 1h10v10H12z" />
                <path fill="#05a6f0" d="M1 12h10v10H1z" />
                <path fill="#ffba08" d="M12 12h10v10H12z" />
              </svg>
              {t.login.azureBtn ?? 'Iniciar sesión con Microsoft'}
            </button>

            <div className="login-divider">{t.login.dividerOr ?? 'o'}</div>
          </>
        )}

        {authMode === 'local' && <form onSubmit={(event) => void handleSubmit(event)}>
          <div className="login-field">
            <label>{t.login.emailL}</label>
            <input
              type="email"
              className="login-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.login.emailPh}
              autoComplete="username"
            />
          </div>

          <button type="submit" className="login-btn">
            {t.login.signIn}
          </button>
        </form>}

        {(error || authError) && <p className="login-err">{error || authError}</p>}
      </div>
    </div>
  );
};
