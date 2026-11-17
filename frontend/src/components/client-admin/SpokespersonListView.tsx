'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { clientAdminService } from '../../services/clientAdminService';
import type { ClientSpokesperson } from '../../types/api';
import { Pagination } from '../common/Pagination';

const languageLabel: Record<ClientSpokesperson['preferredLanguage'], string> = {
  es: 'Español',
  en: 'Inglés',
  pt: 'Portugués',
};

function initials(person: ClientSpokesperson): string {
  const source = person.displayName?.trim() || person.email;
  return source
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase())
    .join('');
}

export const SpokespersonListView: React.FC = () => {
  const [spokespersons, setSpokespersons] = useState<ClientSpokesperson[]>([]);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    let active = true;
    clientAdminService.spokespersons()
      .then(items => {
        if (active) setSpokespersons(items);
      })
      .catch(cause => {
        if (active) {
          setError(cause instanceof Error ? cause.message : 'No se pudieron cargar los voceros.');
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('es');
    if (!normalized) return spokespersons;
    return spokespersons.filter(person =>
      `${person.displayName || ''} ${person.email}`.toLocaleLowerCase('es').includes(normalized),
    );
  }, [query, spokespersons]);
  const pageSize = 8;
  const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visiblePage = visible.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div className="canvas-content">
      <div
        className="card"
        style={{
          marginBottom: '10px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          padding: '14px 18px',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--ink)' }}>
            👥 Voceros asignados ({spokespersons.length})
          </div>
          <div style={{ fontSize: '12.5px', color: 'var(--muted)', marginTop: '2px' }}>
            Voceros vinculados por el configurador Maestro a tu organización
          </div>
        </div>
        <label style={{ minWidth: '260px' }}>
          <span className="label" style={{ display: 'block' }}>Buscar vocero</span>
          <input
            className="field"
            type="search"
            value={query}
            onChange={event => {
              setPage(1);
              setQuery(event.target.value);
            }}
            placeholder="Nombre o correo"
          />
        </label>
      </div>

      <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
        {isLoading ? (
          <div role="status" style={{ padding: '30px', textAlign: 'center', color: 'var(--muted)' }}>
            Cargando voceros asignados...
          </div>
        ) : error ? (
          <div role="alert" className="master-error" style={{ padding: '24px' }}>{error}</div>
        ) : spokespersons.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--muted)' }}>
            El configurador Maestro todavía no ha asignado voceros a tu organización.
          </div>
        ) : visible.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--muted)' }}>
            No hay coincidencias para la búsqueda.
          </div>
        ) : (
          <table className="wf">
            <thead>
              <tr>
                <th>Vocero</th>
                <th>Correo</th>
                <th>Idioma preferido</th>
                <th>Estado</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {visiblePage.map(person => (
                <tr key={person.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          width: '30px',
                          height: '30px',
                          borderRadius: '50%',
                          background: 'var(--accent)',
                          color: '#fff',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flex: '0 0 30px',
                          fontSize: '10.5px',
                          fontWeight: 700,
                        }}
                        aria-hidden="true"
                      >
                        {initials(person)}
                      </span>
                      <span style={{ fontWeight: 600 }}>{person.displayName || 'Sin nombre registrado'}</span>
                    </div>
                  </td>
                  <td>{person.email}</td>
                  <td><span className="tagm">{languageLabel[person.preferredLanguage] || person.preferredLanguage}</span></td>
                  <td><span className="pill on" style={{ cursor: 'default' }}>Activo</span></td>
                  <td>
                    <Link
                      href={`/admin/voceros/detalle/?id=${encodeURIComponent(person.id)}`}
                      className="btn"
                      style={{ display: 'inline-flex', whiteSpace: 'nowrap', textDecoration: 'none' }}
                    >
                      Ver detalle →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!isLoading && !error && spokespersons.length > 0 && <Pagination
          page={safePage}
          totalPages={totalPages}
          totalItems={visible.length}
          itemLabel="voceros"
          onPageChange={setPage}
        />}
      </div>
    </div>
  );
};
