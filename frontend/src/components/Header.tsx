import React from 'react';
import logoWithText from '../../assets/logo_with_text.png';

interface HeaderProps {
  error: string | null;
  micError: string | null;
}

const Header: React.FC<HeaderProps> = ({ error, micError }) => {
  return (
    <>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '1.5rem',
        padding: '1rem 1.5rem',
        backgroundColor: '#1e3a5f',
        borderRadius: '8px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        marginLeft: '-16px',
        marginRight: '-16px',
        marginTop: '-16px'
      }}>
        <h1 style={{ margin: 0, color: '#ffffff', fontSize: '1.75rem', fontWeight: '600' }}>Web Form Voice Filler</h1>
        <img 
          src={logoWithText} 
          alt="Web Form Voice Filler Logo" 
          style={{ maxWidth: '300px', height: 'auto' }}
        />
      </div>
      {error && <div data-testid="error" style={{ 
        color: '#c0392b', 
        backgroundColor: '#ffe6e6', 
        padding: '12px 16px', 
        borderRadius: '6px', 
        border: '1px solid #e74c3c',
        marginTop: '1rem',
        fontSize: '14px'
      }}>Error: {error}</div>}
      {micError && <div style={{ 
        color: '#d68910', 
        backgroundColor: '#fff4e6', 
        padding: '12px 16px', 
        borderRadius: '6px', 
        border: '1px solid #f39c12',
        marginTop: '1rem',
        fontSize: '14px'
      }}>Mic Error: {micError}</div>}
    </>
  );
};

export default Header;
