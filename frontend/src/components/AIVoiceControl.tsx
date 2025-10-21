import React from 'react';

interface AIVoiceControlProps {
  sessionId: string | null;
  aiSessionStarted: boolean;
  isAiConnected: boolean;
  showTranscript: boolean;
  transcript: string[];
  startAiSession: () => void;
  stopAiSession: () => void;
  setShowTranscript: (show: boolean) => void;
}

const AIVoiceControl: React.FC<AIVoiceControlProps> = ({
  sessionId,
  aiSessionStarted,
  isAiConnected,
  showTranscript,
  transcript,
  startAiSession,
  stopAiSession,
  setShowTranscript,
}) => {
  if (!sessionId) return null;

  return (
    <section style={{ 
      marginTop: 24, 
      border: '1px solid #d1d5db', 
      padding: '20px 24px',
      backgroundColor: '#ffffff',
      borderRadius: '8px',
      boxShadow: '0 2px 6px rgba(0,0,0,0.08)'
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 16, color: '#1e3a5f', fontSize: '1.35rem', fontWeight: '600' }}>AI Voice Control</h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        {!aiSessionStarted ? (
          <button 
            onClick={startAiSession}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: '600',
              color: '#fff',
              backgroundColor: '#1e3a5f',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s',
              boxShadow: '0 2px 4px rgba(30,58,95,0.3)'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2c5282'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#1e3a5f'}
          >Start AI Session</button>
        ) : (
          <button 
            onClick={stopAiSession}
            style={{
              padding: '10px 20px',
              fontSize: '14px',
              fontWeight: '600',
              color: '#fff',
              backgroundColor: '#6c757d',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s',
              boxShadow: '0 2px 4px rgba(108,117,125,0.3)'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#5a6268'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#6c757d'}
          >Stop AI Session</button>
        )}

        <label style={{ marginLeft: 8, display: 'flex', alignItems: 'center', gap: 8, fontSize: '14px', color: '#4a5568', cursor: 'pointer' }}>
          <input 
            type="checkbox" 
            aria-label="Show Transcript" 
            checked={showTranscript} 
            onChange={e => setShowTranscript(e.target.checked)}
            style={{ width: '18px', height: '18px', cursor: 'pointer', accentColor: '#1e3a5f' }}
          />
          <span>Show Transcript</span>
        </label>
      </div>

      <div style={{ 
        marginTop: 12, 
        padding: '8px 12px', 
        backgroundColor: '#f8f9fa', 
        borderRadius: '6px',
        fontSize: '14px',
        color: '#2c3e50'
      }}>
        <strong>AI Status:</strong> {isAiConnected ? <span style={{color: '#27ae60', fontWeight: '600'}}>Connected</span> : <span style={{color: '#e74c3c', fontWeight: '600'}}>Disconnected</span>}
      </div>
      {showTranscript && aiSessionStarted && (
        <div style={{
          marginTop: 8,
          border: '1px solid #eee',
          padding: 12,
          boxSizing: 'border-box',
          width: 'min(95vw, 900px)',
          maxWidth: '100%',
          minWidth: 300,
          marginLeft: 'auto',
          marginRight: 'auto',
          maxHeight: '60vh',
          overflowY: 'auto',
        }}>
          <h3>Transcript</h3>
          <div style={{ whiteSpace: 'normal', overflowWrap: 'break-word', wordBreak: 'normal', lineHeight: 1.4 }}>
            {transcript.join(' ').trim()}
          </div>
        </div>
      )}
    </section>
  );
};

export default AIVoiceControl;
