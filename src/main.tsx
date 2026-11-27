import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import SecurityPortal from './SecurityPortal';
import './styles.css';

const isSecurityPortal = window.location.pathname.startsWith('/security-portal');

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isSecurityPortal ? <SecurityPortal /> : <App />}
  </React.StrictMode>,
);
