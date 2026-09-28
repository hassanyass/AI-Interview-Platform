import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n.ts'
import App from './App.tsx'
import { configProblems } from './config'
import { ConfigErrorScreen } from './components/ConfigErrorScreen'

// A build with missing VITE_* variables used to render a blank page (the
// Supabase client throws at module load). Show what is missing instead.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {configProblems.length > 0 ? <ConfigErrorScreen problems={configProblems} /> : <App />}
  </StrictMode>,
)
