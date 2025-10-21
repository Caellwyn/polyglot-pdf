import React, { useEffect, useState } from 'react'

const DebugPanel: React.FC<{ isAiConnected: boolean; isListening: boolean }> = ({ isAiConnected, isListening }) => {
  const [micMetrics, setMicMetrics] = useState<any>(null)
  const [aiMetrics, setAiMetrics] = useState<any>(null)
  const [aiState, setAiState] = useState<any>((window as any).__aiWsState ?? null)

  useEffect(() => {
    const iv = setInterval(() => {
      try {
        setMicMetrics((window as any).__micMetrics ?? null)
        setAiMetrics((window as any).__aiMetrics ?? null)
        setAiState((window as any).__aiWsState ?? null)
      } catch (e) {
        // ignore
      }
    }, 500)
    return () => clearInterval(iv)
  }, [])

  return (
    <div style={{ position: 'fixed', right: 12, bottom: 12, background: 'rgba(0,0,0,0.7)', color: 'white', padding: 8, fontSize: 12, zIndex: 9999, borderRadius: 6, maxWidth: 320 }}>
      <div style={{ fontWeight: 'bold', marginBottom: 6 }}>Debug</div>
      <div>AI WS: {String(aiState)} / connected: {String(isAiConnected)}</div>
      <div>Mic: listening: {String(isListening)}</div>
      <div style={{ marginTop: 6 }}>
        <div style={{ fontWeight: 'bold' }}>Mic Metrics</div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(micMetrics, null, 2)}</pre>
      </div>
      <div style={{ marginTop: 6 }}>
        <div style={{ fontWeight: 'bold' }}>AI Metrics</div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(aiMetrics, null, 2)}</pre>
      </div>
    </div>
  )
}

export default DebugPanel
