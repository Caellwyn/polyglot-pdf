import React from 'react'
import ReactDOM from 'react-dom/client'
import { AdultIntakeDemo } from './AdultIntakeDemo'

// Mount the demo app
// NOTE: StrictMode disabled to prevent double-mounting issues with WebSocket connections
// and VAD initialization. StrictMode intentionally mounts/unmounts components twice in
// development to catch side effects, but this breaks our audio/WebSocket lifecycle.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <AdultIntakeDemo />
)
