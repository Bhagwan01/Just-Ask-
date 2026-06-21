import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000,
        style: {
          background: 'var(--surface-elevated)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border)',
          backdropFilter: 'blur(12px)',
        },
        success: {
          iconTheme: { primary: 'var(--accent)', secondary: 'var(--bg-primary)' },
        },
        error: {
          iconTheme: { primary: '#ef4444', secondary: 'var(--bg-primary)' },
        },
      }}
    />
    <App />
  </StrictMode>,
)
