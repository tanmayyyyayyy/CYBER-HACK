import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import SecurityPortal from './SecurityPortal';
createRoot(document.getElementById('root')!).render(<React.StrictMode><SecurityPortal /></React.StrictMode>);
