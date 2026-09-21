'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useAuth } from '../../context/AuthContext';
import { UserSession } from '../../types/api';

interface LoginViewProps {
  onLoginSuccess?: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const { t } = useI18n();
  const { loginAs, loginWithEmail, testUsers } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

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

  const handleSelectTestUser = (user: UserSession) => {
    loginAs(user);
    if (onLoginSuccess) onLoginSuccess();
  };

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

          {error && <p className="login-err">{error}</p>}
        </form>

        <div className="login-divider">{t.login.testL}</div>

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
      </div>
    </div>
  );
};
