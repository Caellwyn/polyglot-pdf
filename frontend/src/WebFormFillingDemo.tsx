/**
 * WebFormFillingDemo - Example component using the web form filling hook
 * 
 * Demonstrates how to integrate voice filling with any web form.
 */

import React, { useState } from "react";
import { useWebFormFilling } from "./useWebFormFilling";
import { FormSchema } from "./webFormState";

export function WebFormFillingDemo() {
  // Example schema (would come from webParser in production)
  const [schema] = useState<FormSchema>({
    source: "web",
    form_metadata: {
      title: "Contact Form",
      url: window.location.href,
    },
    fields: [
      {
        id: "name",
        name: "Full Name",
        type: "text",
        required: true,
      },
      {
        id: "email",
        name: "Email Address",
        type: "text",
        required: true,
      },
      {
        id: "phone",
        name: "Phone Number",
        type: "text",
        required: false,
      },
      {
        id: "message",
        name: "Message",
        type: "text",
        required: true,
      },
    ],
  });
  
  const {
    status,
    sessionId,
    isConnected,
    formState,
  completionPercentage,
  connect,
  disconnect,
  updateField,
  flushField,
  startRecording,
  stopRecording,
  isRecording,
    reset,
  } = useWebFormFilling({
    schema,
    wsUrl: "ws://localhost:8000/ws/fill",
    autoConnect: false,
    onFieldUpdate: (fieldId, value) => {
      console.log(`Field updated: ${fieldId} = ${value}`);
      
      // In production, you would update the actual form field here
      const element = document.getElementById(fieldId) as HTMLInputElement;
      if (element) {
        element.value = String(value);
        element.dispatchEvent(new Event("change", { bubbles: true }));
      }
    },
    onError: (error) => {
      alert(`Error: ${error.message}`);
    },
  });
  
  // Get field value from state
  const getFieldValue = (fieldId: string): string => {
    return String(formState?.current_values[fieldId]?.value || "");
  };
  
  // Get field confirmation status
  const isFieldConfirmed = (fieldId: string): boolean => {
    return formState?.current_values[fieldId]?.confirmed || false;
  };
  
  return (
    <div style={{ padding: "20px", maxWidth: "800px", margin: "0 auto" }}>
      <h1>Web Form Voice Filling Demo</h1>
      
      {/* Connection Status */}
      <div style={{
        padding: "10px",
        marginBottom: "20px",
        backgroundColor: isConnected ? "#d4edda" : "#f8d7da",
        border: `1px solid ${isConnected ? "#c3e6cb" : "#f5c6cb"}`,
        borderRadius: "4px",
      }}>
        <strong>Status:</strong> {status}
        {sessionId && <> | <strong>Session:</strong> {sessionId}</>}
        {isConnected && <> | <strong>Completion:</strong> {completionPercentage}%</>}
      </div>
      
      {/* Connection Controls */}
      <div style={{ marginBottom: "20px" }}>
        {!isConnected ? (
          <button
            onClick={connect}
            style={{
              padding: "10px 20px",
              fontSize: "16px",
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Connect
          </button>
        ) : (
          <>
            <button
              onClick={disconnect}
              style={{
                padding: "10px 20px",
                fontSize: "16px",
                backgroundColor: "#dc3545",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                marginRight: "10px",
              }}
            >
              Disconnect
            </button>
            
            <button
              onClick={isRecording ? stopRecording : startRecording}
              style={{
                padding: "10px 20px",
                fontSize: "16px",
                backgroundColor: isRecording ? "#ffc107" : "#28a745",
                color: isRecording ? "#000" : "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                marginRight: "10px",
              }}
            >
              {isRecording ? "🎤 Stop Recording" : "🎙️ Start Recording"}
            </button>
            
            <button
              onClick={reset}
              style={{
                padding: "10px 20px",
                fontSize: "16px",
                backgroundColor: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              Reset
            </button>
          </>
        )}
      </div>
      
      {/* Form Fields */}
      <div style={{
        backgroundColor: "#f8f9fa",
        padding: "20px",
        borderRadius: "4px",
        border: "1px solid #dee2e6",
      }}>
        <h2>Contact Form</h2>
        
        {schema.fields.map((field) => (
          <div key={field.id} style={{ marginBottom: "15px" }}>
            <label
              htmlFor={field.id}
              style={{
                display: "block",
                marginBottom: "5px",
                fontWeight: "bold",
              }}
            >
              {field.name}
              {field.required && <span style={{ color: "red" }}>*</span>}
              {isFieldConfirmed(field.id) && (
                <span
                  style={{
                    marginLeft: "10px",
                    fontSize: "12px",
                    color: "#28a745",
                    fontWeight: "normal",
                  }}
                >
                  ✓ AI Confirmed
                </span>
              )}
            </label>
            
            <input
              id={field.id}
              type="text"
              value={getFieldValue(field.id)}
              onChange={(e) => updateField(field.id, e.target.value, { confirmed: false })}
              onBlur={(e) => {
                updateField(field.id, e.target.value, { confirmed: true });
                flushField(field.id);
              }}
              disabled={!isConnected}
              style={{
                width: "100%",
                padding: "8px",
                fontSize: "14px",
                border: "1px solid #ced4da",
                borderRadius: "4px",
                backgroundColor: isFieldConfirmed(field.id) ? "#e7f3e7" : "white",
              }}
            />
          </div>
        ))}
        
        <button
          type="submit"
          style={{
            padding: "10px 30px",
            fontSize: "16px",
            backgroundColor: completionPercentage === 100 ? "#28a745" : "#6c757d",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: completionPercentage === 100 ? "pointer" : "not-allowed",
          }}
          disabled={completionPercentage !== 100}
        >
          Submit Form
        </button>
      </div>
      
      {/* Debug Info */}
      {formState && (
        <details style={{ marginTop: "20px" }}>
          <summary style={{ cursor: "pointer", fontWeight: "bold" }}>
            Debug Info
          </summary>
          <pre style={{
            backgroundColor: "#f8f9fa",
            padding: "10px",
            borderRadius: "4px",
            overflow: "auto",
            fontSize: "12px",
          }}>
            {JSON.stringify(formState, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
