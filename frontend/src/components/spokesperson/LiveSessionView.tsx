'use client';

import React, { useState } from 'react';
import { useI18n } from '../../context/I18nContext';
import type { SessionSetup } from '../../services/sessionFlowService';
import type { VoceroScreen } from './HomePracticeView';

interface Props {
  setup: SessionSetup;
  onNavigate: (screen: VoceroScreen) => void;
}

export const LiveSessionView: React.FC<Props> = ({ setup, onNavigate }) => {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  const questions = setup.questions;

  return <div className="canvas-content">
    <div className="grid2" style={{ marginBottom: 16 }}>
      <div className="vid" style={{ minHeight: 260 }}>
        <span className="tag">{t.L.u4.interviewer}</span>
      </div>
      <div className="self" style={{ minHeight: 260, padding: 24 }}>
        La comprobación técnica terminó. Cámara y micrófono se liberaron al salir de esa pantalla.
      </div>
    </div>
    <div className="card" style={{ marginBottom: 16, borderLeft: '4px solid var(--accent2)' }}>
      <div className="label">Pregunta de esta sesión</div>
      <p style={{ fontSize: 17 }}>{questions[index]?.text}</p>
    </div>
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
      <button type="button" className="btn" disabled={index === 0} onClick={() => setIndex(index - 1)}>Anterior</button>
      <span>Pregunta {index + 1} de {questions.length}</span>
      <button type="button" className="btn pri" disabled={index >= questions.length - 1}
        onClick={() => setIndex(index + 1)}>Siguiente pregunta</button>
      <button type="button" className="btn ghost" onClick={() => onNavigate('u2')}>Salir</button>
    </div>
  </div>;
};
