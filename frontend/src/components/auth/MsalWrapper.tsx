'use client';

import React from 'react';
import { MsalProvider } from '@azure/msal-react';
import { msalInstance, isAzureConfigured } from '../../services/authConfig';

interface MsalWrapperProps {
  children: React.ReactNode;
}

/**
 * Client-side wrapper that initialises MSAL and provides the MsalProvider
 * context to the rest of the component tree.
 *
 * When Azure credentials are not configured (e.g. pure local dev without
 * Entra), the wrapper renders children directly without MsalProvider so the
 * app can still function with the mock/demo login flow.
 */
export function MsalWrapper({ children }: MsalWrapperProps) {
  if (!isAzureConfigured) {
    return <>{children}</>;
  }

  return (
    <MsalProvider instance={msalInstance}>
      {children}
    </MsalProvider>
  );
}
