import { Suspense } from 'react';
import { SpokespersonDetailRoute } from '../../../../../components/client-admin/SpokespersonDetailRoute';

function DetailFallback() {
  return (
    <div className="platform-container">
      <main className="canvas">
        <div className="canvas-content">
          <div className="card" role="status" style={{ minHeight: '420px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '14px', color: 'var(--muted)' }}>
            <div className="upload-overlay-spinner" style={{ width: '42px', height: '42px' }} />
            <strong style={{ color: 'var(--ink)', fontSize: '14px' }}>Abriendo detalle del vocero...</strong>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function ClientSpokespersonDetailPage() {
  return (
    <Suspense fallback={<DetailFallback />}>
      <SpokespersonDetailRoute />
    </Suspense>
  );
}
