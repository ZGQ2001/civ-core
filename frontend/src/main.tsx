import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { DialogsProvider } from './components/Dialogs.tsx';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DialogsProvider>
      <App />
    </DialogsProvider>
  </StrictMode>,
);
