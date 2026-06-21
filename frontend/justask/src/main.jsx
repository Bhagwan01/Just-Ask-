import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'var(--surface-elevated)',
            color: 'var(--text-primary)',
            border: 'var(--border-width) solid var(--border)',
            boxShadow: 'var(--shadow-md)',
            borderRadius: '0',
            fontFamily: 'var(--font-sans)',
            fontWeight: '600',
          },
          success: {
            iconTheme: { primary: 'var(--success)', secondary: 'var(--bg-primary)' },
          },
          error: {
            iconTheme: { primary: 'var(--error)', secondary: 'var(--bg-primary)' },
          },
        }}
      />
      <App />
    </BrowserRouter>
  </StrictMode>,
)
