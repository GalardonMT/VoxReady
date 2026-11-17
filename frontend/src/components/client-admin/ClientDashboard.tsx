'use client';

import React from 'react';
import { BookOpenCheck, ChevronRight, ShieldCheck } from 'lucide-react';

export type AdminScreen = 'a1' | 'a3' | 'a4';

interface ClientDashboardProps {
  onNavigate: (screen: AdminScreen) => void;
}

export const ClientDashboard: React.FC<ClientDashboardProps> = ({ onNavigate }) => {
  return (
    <div className="canvas-content client-dashboard-home">
      <section className="client-dashboard-welcome" aria-labelledby="client-dashboard-title">
        <span className="client-dashboard-eyebrow">Administración del cliente</span>
        <h1 id="client-dashboard-title">Panel del Cliente</h1>
        <p>
          Consulta los escenarios habilitados para tu organización y revisa la política de
          conservación de la información.
        </p>
      </section>

      <section className="client-dashboard-links" aria-label="Opciones del panel">
        <button
          type="button"
          className="client-dashboard-link"
          onClick={() => onNavigate('a4')}
        >
          <span className="client-dashboard-link-icon" aria-hidden="true">
            <BookOpenCheck size={24} strokeWidth={1.8} />
          </span>
          <span className="client-dashboard-link-copy">
            <strong>Escenarios disponibles</strong>
            <span>Revisa el contexto, los mensajes clave, las líneas rojas y las preguntas.</span>
          </span>
          <ChevronRight className="client-dashboard-link-arrow" aria-hidden="true" />
        </button>

        <button
          type="button"
          className="client-dashboard-link"
          onClick={() => onNavigate('a3')}
        >
          <span className="client-dashboard-link-icon client-dashboard-link-icon--shield" aria-hidden="true">
            <ShieldCheck size={24} strokeWidth={1.8} />
          </span>
          <span className="client-dashboard-link-copy">
            <strong>Política de Retención</strong>
            <span>Consulta las reglas aplicables a grabaciones, métricas y solicitudes.</span>
          </span>
          <ChevronRight className="client-dashboard-link-arrow" aria-hidden="true" />
        </button>
      </section>
    </div>
  );
};
