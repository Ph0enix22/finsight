import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.tsx'
import './index.css'
import { MOCK_MODE } from './lib/api'

async function enableMocking() {
  if (!MOCK_MODE) return
  const { worker } = await import('./mocks/browser')
  await worker.start()
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
