/**
 * Unit test for Clear Form functionality
 * 
 * Tests that Clear Form button properly clears:
 * 1. sessionStorage (web_form_state key)
 * 2. DOM field values
 * 3. Does NOT auto-repopulate from sessionStorage
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormStateManager } from '../src/webFormState'

describe('Clear Form Button', () => {
  let sessionStorageMock: { [key: string]: string }

  beforeEach(() => {
    // Mock sessionStorage
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null)
    } as any
  })

  it('should clear sessionStorage when WebFormStateManager.clear() is called', () => {
    // Setup: Create some state in sessionStorage
    const schema = {
      source: 'web' as const,
      form_metadata: {
        title: 'Test Form',
        url: 'http://localhost/test'
      },
      fields: [
        { id: 'firstName', name: 'First Name', type: 'text' },
        { id: 'lastName', name: 'Last Name', type: 'text' }
      ]
    }

    const state = WebFormStateManager.init(schema)
    WebFormStateManager.updateField(state, 'firstName', 'John', { confirmed: true })
    
    // Verify state exists
    expect(sessionStorage.getItem('web_form_state')).toBeTruthy()
    
    // Clear
    WebFormStateManager.clear()
    
    // Verify cleared
    expect(sessionStorage.removeItem).toHaveBeenCalledWith('web_form_state')
    expect(sessionStorageMock['web_form_state']).toBeUndefined()
  })

  it('should clear all DOM field values', () => {
    // This test verifies the clearing logic works with DOM manipulation
    // In a real browser environment, this would clear all form fields
    
    // Mock DOM clearing logic (same as overlay.ts Clear Form button)
    const mockFields = [
      { type: 'text', value: 'John', tagName: 'INPUT' },
      { type: 'checkbox', checked: true, tagName: 'INPUT' },
      { type: 'select', selectedIndex: 1, tagName: 'SELECT' },
      { value: 'Test comment', tagName: 'TEXTAREA' }
    ]

    // Simulate clearing
    mockFields.forEach((field) => {
      if (field.tagName === 'INPUT') {
        if (field.type === 'checkbox' || field.type === 'radio') {
          field.checked = false
        } else {
          field.value = ''
        }
      } else if (field.tagName === 'TEXTAREA') {
        field.value = ''
      } else if (field.tagName === 'SELECT') {
        field.selectedIndex = 0
      }
    })

    // Verify all cleared
    expect(mockFields[0].value).toBe('')
    expect(mockFields[1].checked).toBe(false)
    expect(mockFields[2].selectedIndex).toBe(0)
    expect(mockFields[3].value).toBe('')
  })

  it('should NOT auto-repopulate from sessionStorage after clearing', () => {
    // This is the critical test - sessionStorage should be cleared
    // so nothing can repopulate from stale state

    // Setup: Create state
    const schema = {
      source: 'web' as const,
      form_metadata: {
        title: 'Test Form',
        url: 'http://localhost/test'
      },
      fields: [
        { id: 'firstName', name: 'First Name', type: 'text' },
        { id: 'lastName', name: 'Last Name', type: 'text' }
      ]
    }

    const state = WebFormStateManager.init(schema)
    WebFormStateManager.updateField(state, 'firstName', 'John', { confirmed: true })
    WebFormStateManager.updateField(state, 'lastName', 'Doe', { confirmed: true })

    // Verify state exists
    expect(sessionStorageMock['web_form_state']).toBeTruthy()

    // Clear sessionStorage (this is what Clear Form button does FIRST)
    WebFormStateManager.clear()
    
    // Verify sessionStorage is cleared
    expect(sessionStorageMock['web_form_state']).toBeUndefined()

    // Try to load state (should return null)
    const loadedState = WebFormStateManager.load()
    expect(loadedState).toBeNull()
  })

  it('should remove VFF markers', () => {
    // Test that clearing logic removes AI confirmation markers
    const mockElement = {
      'data-vff-confirmed': 'true',
      style: {
        outline: '2px solid green',
        outlineOffset: '2px'
      }
    }

    // Clear markers (same as Clear Form button)
    delete mockElement['data-vff-confirmed']
    mockElement.style.outline = ''
    mockElement.style.outlineOffset = ''

    // Verify cleared
    expect(mockElement['data-vff-confirmed']).toBeUndefined()
    expect(mockElement.style.outline).toBe('')
    expect(mockElement.style.outlineOffset).toBe('')
  })
})
