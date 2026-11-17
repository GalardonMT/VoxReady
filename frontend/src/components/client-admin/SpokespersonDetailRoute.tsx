'use client';

import React from 'react';
import { useSearchParams } from 'next/navigation';
import { SpokespersonDetailPage } from './SpokespersonDetailPage';

export const SpokespersonDetailRoute: React.FC = () => {
  const searchParams = useSearchParams();
  const spokespersonId = searchParams.get('id')?.trim();

  if (!spokespersonId) {
    return (
      <div className="platform-container">
        <main className="canvas">
          <div className="canvas-content">
            <div className="card master-error" role="alert">
              No se indicó el vocero que se desea consultar.
            </div>
          </div>
        </main>
      </div>
    );
  }

  return <SpokespersonDetailPage spokespersonId={spokespersonId} />;
};
