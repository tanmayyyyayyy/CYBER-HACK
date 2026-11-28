import React from 'react';
import { createRoot } from 'react-dom/client';

async function start() {
  const path = window.location.pathname;
  if (path.startsWith('/security-portal')) {
    await import('./SecurityEntry');
  } else if (path.startsWith('/legacy')) {
    await import('./LegacyEntry');
  } else {
    const { default: GuidedApp } = await import('./GuidedApp');
    createRoot(document.getElementById('root')!).render(<React.StrictMode><GuidedApp /></React.StrictMode>);
  }
}
void start();
