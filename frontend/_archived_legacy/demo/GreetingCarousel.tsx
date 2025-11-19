import React, { useState, useEffect } from 'react'
import { GREETING_PROMPTS } from '../shared/greetingPrompts'

interface GreetingCarouselProps {
  /** Milliseconds between language transitions */
  intervalMs?: number
  /** Called when user dismisses the carousel */
  onDismiss?: () => void
}

/**
 * Language carousel that cycles through greetings in different languages
 * Prompts user to say "Hello Gemini" in their native language
 * Shows the multilingual capability of the AI assistant
 */
export function GreetingCarousel({ 
  intervalMs = 3000, 
  onDismiss 
}: GreetingCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [fadeState, setFadeState] = useState<'in' | 'out'>('in')
  
  useEffect(() => {
    // Cycle through languages
    const cycleInterval = setInterval(() => {
      // Fade out
      setFadeState('out')
      
      // After fade out, change language and fade in
      setTimeout(() => {
        setCurrentIndex((prev) => (prev + 1) % GREETING_PROMPTS.length)
        setFadeState('in')
      }, 300) // Match CSS transition duration
      
    }, intervalMs)
    
    return () => clearInterval(cycleInterval)
  }, [intervalMs])
  
  const currentPrompt = GREETING_PROMPTS[currentIndex]
  
  return (
    <div className="greeting-carousel">
      <div className="greeting-carousel__content">
        {/* Microphone icon */}
        <div className="greeting-carousel__icon">
          <svg 
            width="48" 
            height="48" 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            strokeWidth="2"
            strokeLinecap="round" 
            strokeLinejoin="round"
          >
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" x2="12" y1="19" y2="22"/>
          </svg>
        </div>
        
        {/* Rotating text */}
        <div 
          className={`greeting-carousel__text greeting-carousel__text--${fadeState}`}
          key={currentIndex}
        >
          <div className="greeting-carousel__language">
            {currentPrompt.language}
          </div>
          <div className="greeting-carousel__prompt">
            {currentPrompt.text}
          </div>
        </div>
        
        {/* Progress indicator */}
        <div className="greeting-carousel__progress">
          {GREETING_PROMPTS.map((_, idx) => (
            <div 
              key={idx}
              className={`greeting-carousel__dot ${idx === currentIndex ? 'greeting-carousel__dot--active' : ''}`}
            />
          ))}
        </div>
      </div>
      
      {/* Optional dismiss button */}
      {onDismiss && (
        <button 
          className="greeting-carousel__dismiss"
          onClick={onDismiss}
          aria-label="Dismiss greeting prompt"
        >
          ×
        </button>
      )}
      
      <style>{`
        .greeting-carousel {
          position: fixed;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 3rem 4rem;
          border-radius: 20px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          z-index: 1000;
          max-width: 600px;
          width: 90%;
        }
        
        .greeting-carousel__content {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1.5rem;
        }
        
        .greeting-carousel__icon {
          animation: pulse 2s ease-in-out infinite;
        }
        
        .greeting-carousel__icon svg {
          color: white;
          filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.2));
        }
        
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.05); opacity: 0.9; }
        }
        
        .greeting-carousel__text {
          text-align: center;
          min-height: 120px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          transition: opacity 0.3s ease-in-out, transform 0.3s ease-in-out;
        }
        
        .greeting-carousel__text--in {
          opacity: 1;
          transform: translateY(0);
        }
        
        .greeting-carousel__text--out {
          opacity: 0;
          transform: translateY(-10px);
        }
        
        .greeting-carousel__language {
          font-size: 0.875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          opacity: 0.9;
          margin-bottom: 0.5rem;
        }
        
        .greeting-carousel__prompt {
          font-size: 1.5rem;
          font-weight: 500;
          line-height: 1.4;
          text-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .greeting-carousel__progress {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          justify-content: center;
          max-width: 300px;
        }
        
        .greeting-carousel__dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.3);
          transition: all 0.3s ease;
        }
        
        .greeting-carousel__dot--active {
          width: 24px;
          border-radius: 3px;
          background: white;
        }
        
        .greeting-carousel__dismiss {
          position: absolute;
          top: 1rem;
          right: 1rem;
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          font-size: 2rem;
          line-height: 1;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s;
        }
        
        .greeting-carousel__dismiss:hover {
          background: rgba(255, 255, 255, 0.3);
        }
        
        @media (max-width: 640px) {
          .greeting-carousel {
            padding: 2rem;
          }
          
          .greeting-carousel__prompt {
            font-size: 1.25rem;
          }
          
          .greeting-carousel__progress {
            display: none; /* Too many dots on mobile */
          }
        }
      `}</style>
    </div>
  )
}
