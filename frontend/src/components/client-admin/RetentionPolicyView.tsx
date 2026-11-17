'use client';

import React, { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { clientAdminService } from '../../services/clientAdminService';
import type { ClientRetentionPolicy } from '../../types/api';

const KEEP_LABELS: Record<NonNullable<ClientRetentionPolicy['keep']>, string> = {
  full_recording: 'Grabación completa y métricas',
  metrics_only: 'Solo métricas',
};

export const RetentionPolicyView: React.FC = () => {
  const [policy, setPolicy] = useState<ClientRetentionPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    clientAdminService.retentionPolicy()
      .then((response) => {
        if (active) setPolicy(response);
      })
      .catch(() => {
        if (active) setError('No pudimos consultar la política de retención vigente.');
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="canvas-content" aria-labelledby="retention-policy-title">
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ShieldCheck size={24} aria-hidden="true" />
          <div>
            <h1 id="retention-policy-title" style={{ margin: 0 }}>Política de Retención</h1>
            <p style={{ color: 'var(--muted)', marginBottom: 0 }}>
              Consulta la configuración vigente de tu organización. Esta vista es de solo lectura.
            </p>
          </div>
        </div>

        {!policy && !error && (
          <p role="status" style={{ marginTop: '24px' }}>Cargando política vigente...</p>
        )}

        {error && (
          <p role="alert" style={{ color: 'var(--danger)', marginTop: '24px' }}>{error}</p>
        )}

        {policy && !policy.configured && (
          <p role="status" style={{ marginTop: '24px' }}>
            Tu organización todavía no tiene una política de retención vigente configurada.
          </p>
        )}

        {policy?.configured && (
          <dl className="grid3" style={{ marginTop: '24px' }}>
            <div className="stat">
              <dt className="k">Conservación</dt>
              <dd className="v" style={{ fontSize: '18px' }}>
                {policy.keep ? KEEP_LABELS[policy.keep] : 'No informada'}
              </dd>
            </div>
            <div className="stat">
              <dt className="k">Plazo</dt>
              <dd className="v">{policy.termDays === null ? '—' : `${policy.termDays} días`}</dd>
            </div>
            <div className="stat">
              <dt className="k">Versión</dt>
              <dd className="v" style={{ fontSize: '18px' }}>{policy.version ?? '—'}</dd>
            </div>
          </dl>
        )}
      </div>
    </section>
  );
};
