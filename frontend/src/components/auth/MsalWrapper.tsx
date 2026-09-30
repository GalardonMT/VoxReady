'use client';

import React, { useEffect, useState } from 'react';
import { MsalProvider } from '@azure/msal-react';
import { msalInstance, isAzureConfigured } from '../../services/authConfig';

interface MsalWrapperProps {
  children: React.ReactNode;
}

/**
 * Client-side wrapper that initialises MSAL and provides the MsalProvider
 * context to the rest of the component tree.
 *
 * MSAL v5 requires explicit initialisation (`initialize()`) and processing of
 * any pending redirect responses (`handleRedirectPromise()`) before the
 * library can be used. This wrapper handles both steps and only renders the
 * children once MSAL is fully ready.
 *
 * When Azure credentials are not configured (e.g. pure local dev without
 * Entra), the wrapper renders children directly without MsalProvider so the
 * app can still function with the mock/demo login flow.
 */
export function MsalWrapper({ children }: MsalWrapperProps) {
  const [ready, setReady] = useState(!isAzureConfigured);

  useEffect(() => {
    if (!isAzureConfigured) return;

    msalInstance
      .initialize()
      .then(() => msalInstance.handleRedirectPromise())
      .then(() => {
        setReady(true);
      })
      .catch((err) => {
        console.error('[MSAL] Initialization failed:', err);
        // Still render the app so the fallback / test-user login works
        setReady(true);
      });
  }, []);

  if (!ready) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
        }}
      >
        <p style={{ color: 'var(--muted, #888)', fontSize: '14px' }}>
          Cargando…
        </p>
      </div>
    );
  }

  if (!isAzureConfigured) {
    return <>{children}</>;
  }

  return (
    <MsalProvider instance={msalInstance}>
      {children}
    </MsalProvider>
  );
}
