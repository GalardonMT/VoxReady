'use client';

import React from 'react';

interface WindowChromeProps {
  url: string;
  children: React.ReactNode;
}

export const WindowChrome: React.FC<WindowChromeProps> = ({ url, children }) => {
  return (
    <div className="chrome">
      <div className="chrome-bar">
        <span className="dot red" />
        <span className="dot yellow" />
        <span className="dot green" />
        <div className="urlbar">
          <span style={{ opacity: 0.6, fontSize: '11px' }}>🔒 https://</span>
          <span style={{ fontWeight: 500, color: 'var(--ink)' }}>{url}</span>
        </div>
      </div>
      <div className="canvas">{children}</div>
    </div>
  );
};
