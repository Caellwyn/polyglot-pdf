import React from 'react';

interface WebSocketEchoTestProps {
  wsConnected: boolean;
  helloAck: boolean;
  lastServerPing: number | null;
  wsMessages: string[];
  connectWs: () => void;
  disconnectWs: () => void;
  sendPing: () => void;
}

const WebSocketEchoTest: React.FC<WebSocketEchoTestProps> = ({
  wsConnected,
  helloAck,
  lastServerPing,
  wsMessages,
  connectWs,
  disconnectWs,
  sendPing,
}) => {
  return (
    <details style={{ marginTop: 16 }}>
      <summary>WebSocket Echo Test</summary>
      <div style={{ marginTop: 8 }}>
        <button onClick={connectWs} disabled={wsConnected}>Connect</button>
        <button onClick={disconnectWs} disabled={!wsConnected}>Disconnect</button>
        <button onClick={sendPing} disabled={!wsConnected}>Send Ping</button>
      </div>
      <div>Status: {wsConnected ? 'connected' : 'disconnected'}</div>
      <div>Hello ACK: {helloAck ? '✅' : '❌'}</div>
      <div>Last Server Ping: {lastServerPing ? new Date(lastServerPing).toLocaleTimeString() : 'never'}</div>
      <pre style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid #ccc', padding: 8 }}>
        {wsMessages.map((m, i) => <div key={i}>{m}</div>)}
      </pre>
    </details>
  );
};

export default WebSocketEchoTest;
