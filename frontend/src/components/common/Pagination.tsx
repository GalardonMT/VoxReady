'use client';

import React from 'react';

function paginationItems(current: number, total: number): Array<number | 'ellipsis-left' | 'ellipsis-right'> {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set([1, total, current - 1, current, current + 1]);
  const visible = [...pages].filter(page => page >= 1 && page <= total).sort((a, b) => a - b);
  const items: Array<number | 'ellipsis-left' | 'ellipsis-right'> = [];
  visible.forEach((page, index) => {
    const previous = visible[index - 1];
    if (previous && page - previous > 1) {
      items.push(previous === 1 ? 'ellipsis-left' : 'ellipsis-right');
    }
    items.push(page);
  });
  return items;
}

interface PaginationProps {
  page: number;
  totalPages: number;
  totalItems: number;
  itemLabel: string;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  page,
  totalPages,
  totalItems,
  itemLabel,
  onPageChange,
}) => {
  if (totalItems === 0) return null;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', padding: '12px 16px', borderTop: '1px solid var(--line)', flexWrap: 'wrap' }}>
      <button type="button" className="btn" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Anterior</button>
      <nav aria-label={`Páginas de ${itemLabel}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', flexWrap: 'wrap' }}>
        {paginationItems(page, totalPages).map(item => typeof item === 'number' ? (
          <button
            type="button"
            key={item}
            className={`btn ${item === page ? 'nav' : ''}`}
            aria-current={item === page ? 'page' : undefined}
            aria-label={`Ir a la página ${item}`}
            onClick={() => onPageChange(item)}
            style={{ minWidth: '34px', padding: '6px 9px' }}
          >
            {item}
          </button>
        ) : (
          <span key={item} aria-hidden="true" style={{ padding: '0 4px', color: 'var(--muted)' }}>…</span>
        ))}
      </nav>
      <button type="button" className="btn" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Siguiente</button>
      <span className="legend" style={{ flexBasis: '100%', textAlign: 'center' }}>{totalItems} {itemLabel}</span>
    </div>
  );
};
