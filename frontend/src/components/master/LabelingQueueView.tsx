'use client';

import React from 'react';
import { MasterScreen } from './MasterDashboard';

interface LabelingQueueViewProps {
  onNavigate?: (screen: MasterScreen) => void;
}

export const LabelingQueueView: React.FC<LabelingQueueViewProps> = () => (
  <div className="canvas-content">
    <div className="card col" role="status" aria-live="polite">
      <h2>Cola de etiquetado</h2>
      <p>
        Esta funcionalidad está en desarrollo y no forma parte de esta versión estable.
        No se muestran casos ni puntuaciones simuladas.
      </p>
    </div>
  </div>
);
