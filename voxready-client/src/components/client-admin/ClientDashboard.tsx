'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { topicService } from '../../services/topicService';
import { TopicConfig } from '../../types/api';

export type AdminScreen = 'a1' | 'a2' | 'a3';

interface ClientDashboardProps {
  onNavigate: (screen: AdminScreen, topicId?: string | null) => void;
}

export const ClientDashboard: React.FC<ClientDashboardProps> = ({ onNavigate }) => {
  const { t } = useI18n();
  const d = t.L.a1;

  const [topics, setTopics] = useState<TopicConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function loadTopics() {
      setIsLoading(true);
      try {
        const data = await topicService.getTopics();
        if (isMounted) {
          setTopics(data);
        }
      } catch {
        // Manejado por topicService
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }
    loadTopics();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleDelete = async (id: string) => {
    try {
      const updated = await topicService.deleteTopic(id);
      setTopics(updated);
      setDeleteConfirmId(null);
    } catch {
      alert('Error al eliminar el tema.');
    }
  };

  const statValues = [topics.length, 38, 152, 71];

  return (
    <div className="canvas-content">
      {/* KPI Stats */}
      <div className="grid4" style={{ marginBottom: '20px' }}>
        {d.st.map((k, i) => (
          <div key={i} className="stat">
            <div className="k">{k}</div>
            <div className="v">{statValues[i]}</div>
          </div>
        ))}
      </div>

      {/* Themes Table Section Header */}
      <div
        className="card"
        style={{
          marginBottom: '10px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '14px 18px'
        }}
      >
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--ink)' }}>
            📋 {d.themesL} ({topics.length})
          </div>
          <div style={{ fontSize: '12.5px', color: 'var(--muted)', marginTop: '2px' }}>
            Temas y escenarios de crisis configurados para la práctica de tus voceros
          </div>
        </div>
        <button
          type="button"
          className="btn pri"
          onClick={() => onNavigate('a2', 'new')}
        >
          {d.newT}
        </button>
      </div>

      {/* Themes Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--muted)' }}>
            Cargando temas configurados...
          </div>
        ) : topics.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' }}>
            <p style={{ color: 'var(--muted)', fontSize: '14px', marginBottom: '14px' }}>
              No hay temas configurados todavía.
            </p>
            <button
              type="button"
              className="btn pri"
              onClick={() => onNavigate('a2', 'new')}
            >
              ➕ Crear el primer tema
            </button>
          </div>
        ) : (
          <table className="wf">
            <thead>
              <tr>
                <th>{d.th[0] || 'Tema'}</th>
                <th>{d.th[1] || 'Público interno'}</th>
                <th>Óptica</th>
                <th>{d.th[2] || 'Idiomas'}</th>
                <th>{d.th[3] || 'Retención'}</th>
                <th style={{ textAlign: 'right' }}>{d.th[4] || 'Acciones'}</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((topic) => (
                <tr key={topic.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{topic.name}</div>
                    {topic.context && (
                      <div
                        style={{
                          fontSize: '11.5px',
                          color: 'var(--muted)',
                          maxWidth: '280px',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          marginTop: '2px'
                        }}
                      >
                        {topic.context}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="pill on" style={{ fontSize: '11px', padding: '2px 8px' }}>
                      {topic.audience || 'Dirección'}
                    </span>
                  </td>
                  <td>
                    <span
                      style={{
                        fontSize: '11.5px',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: 'var(--soft)',
                        fontWeight: 500
                      }}
                    >
                      {topic.optics || 'Empática'}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {(topic.languages || ['ES']).map((lang) => (
                        <span key={lang} className="tagm" style={{ padding: '1px 6px', fontSize: '10.5px' }}>
                          {lang}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className="tagm">{topic.retention || '90 días'}</span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center' }}>
                      <button
                        type="button"
                        className="btn"
                        style={{ padding: '4px 10px', fontSize: '11.5px' }}
                        onClick={() => onNavigate('a2', topic.id)}
                        title="Editar tema"
                      >
                        ✏️ {d.edit || 'Editar'}
                      </button>

                      {deleteConfirmId === topic.id ? (
                        <div style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
                          <button
                            type="button"
                            className="btn danger"
                            style={{ padding: '4px 8px', fontSize: '11px', background: 'var(--danger)', color: '#fff' }}
                            onClick={() => handleDelete(topic.id)}
                          >
                            Confirmar
                          </button>
                          <button
                            type="button"
                            className="btn ghost"
                            style={{ padding: '4px 6px', fontSize: '11px' }}
                            onClick={() => setDeleteConfirmId(null)}
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn ghost"
                          style={{ padding: '4px 8px', fontSize: '11.5px', color: 'var(--muted)' }}
                          onClick={() => setDeleteConfirmId(topic.id)}
                          title="Eliminar tema"
                        >
                          🗑️
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
