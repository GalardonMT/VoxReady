'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { UserSession } from '../../types/api';
import { isAzureConfigured } from '../../services/authConfig';

interface LoginViewProps {
  onLoginSuccess?: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const { t } = useI18n();
  const { loginAs, loginWithEmail, loginWithAzure, loading, testUsers } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [azureLoading, setAzureLoading] = useState(false);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError('');
    const success = loginWithEmail(email);
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
      // loginRedirect will navigate away — if we reach here it was a popup
      if (onLoginSuccess) onLoginSuccess();
    } catch {
      setError(t.login.azureErr ?? 'Error al iniciar sesión.');
      setAzureLoading(false);
    }
  };

  const handleSelectTestUser = (user: UserSession) => {
    loginAs(user);
    if (onLoginSuccess) onLoginSuccess();
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

        {/* ---- Primary: Azure login ---- */}
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

            <div className="login-divider">{t.login.testL}</div>
          </>
        )}

        {/* ---- Secondary: email/password form ---- */}
        {!isAzureConfigured && (
          <>
            <form onSubmit={handleSubmit}>
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

              <div className="login-field">
                <label>{t.login.passL}</label>
                <input
                  type="password"
                  className="login-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t.login.passPh}
                  autoComplete="current-password"
                />
              </div>

              <button type="submit" className="login-btn">
                {t.login.signIn}
              </button>
            </form>

            {error && <p className="login-err">{error}</p>}

            <div className="login-divider">{t.login.testL}</div>
          </>
        )}

        {/* ---- Test users (always visible as fallback) ---- */}
        <div>
          {testUsers.map((user) => (
            <button
              key={user.userId}
              type="button"
              className="tu"
              onClick={() => handleSelectTestUser(user)}
            >
              <span className="tuava">{user.initials}</span>
              <span className="tumeta">
                <span className="tuname">{user.displayName}</span>
                <span className="turole">
                  {t.roles[user.role]} · {user.email}
                </span>
              </span>
              <span className="tugo">→</span>
            </button>
          ))}
        </div>

        {error && isAzureConfigured && <p className="login-err">{error}</p>}
      </div>
    </div>
  );
};
