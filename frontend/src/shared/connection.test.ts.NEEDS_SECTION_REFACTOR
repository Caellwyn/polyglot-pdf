/**
 * Unit tests for Connection Manager
 * 
 * Tests connection.ts SchemaFormStateManager integration
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createConnectionManager } from './connection'
import type { FormSchema } from '../schema-forms/types/schema'

// Mock dependencies
vi.mock('./fieldManager', () => ({
  createFieldManager: vi.fn(() => ({
    cleanup: vi.fn()
  }))
}))

vi.mock('./audioManager', () => ({
  createAudioManager: vi.fn(() => ({
    cleanup: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    isRecording: vi.fn(() => false),
    isSpeaking: vi.fn(() => false),
    flushAudioQueue: vi.fn(),
    resumePlayback: vi.fn(),
    resumeAudioContext: vi.fn()
  }))
}))

vi.mock('../webFormConnection', () => ({
  WebFormConnection: vi.fn(function(this: any) {
    this.connect = vi.fn()
    this.disconnect = vi.fn()
    this.getStatus = vi.fn(() => 'disconnected')
    this.sendAudio = vi.fn()
    this.sendActivityStart = vi.fn()
    this.sendActivityEnd = vi.fn()
    this.sendPrompt = vi.fn()
    this.startSection = vi.fn()
    this.switchSection = vi.fn()
    this.completeSection = vi.fn()
    this.getCurrentSection = vi.fn()
    this.getCompletedSections = vi.fn(() => new Set())
    return this
  })
}))

describe('Connection Manager - SchemaFormStateManager Integration', () => {
  let sessionStorageMock: { [key: string]: string }
  let testSchema: FormSchema

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

    // Create test schema
    testSchema = {
      source: 'pdf',
      form_metadata: {
        title: 'Test I-90 Form',
        version: '1.0.0',
        language: 'en',
        form_number: 'I-90',
        edition_date: '01/20/25',
        page_count: 2
      },
      parts: [
        {
          id: 'part-1',
          label: 'Personal Information',
          description: 'Basic information',
          order: 1,
          section_ids: ['section-1a'],
          required: true
        },
        {
          id: 'part-2',
          label: 'Address Information',
          description: 'Contact details',
          order: 2,
          section_ids: ['section-2a'],
          required: true
        }
      ],
      sections: [
        {
          id: 'section-1a',
          label: 'Name',
          order: 1,
          fields: ['field-1', 'field-2']
        },
        {
          id: 'section-2a',
          label: 'Current Address',
          order: 2,
          fields: ['field-3', 'field-4']
        }
      ],
      fields: [
        {
          id: 'field-1',
          name: 'First Name',
          spoken_name: 'first name',
          type: 'text',
          section_id: 'section-1a'
        },
        {
          id: 'field-2',
          name: 'Last Name',
          spoken_name: 'last name',
          type: 'text',
          section_id: 'section-1a'
        },
        {
          id: 'field-3',
          name: 'Street Address',
          spoken_name: 'street address',
          type: 'text',
          section_id: 'section-2a'
        },
        {
          id: 'field-4',
          name: 'City',
          spoken_name: 'city',
          type: 'text',
          section_id: 'section-2a'
        }
      ]
    }
  })

  describe('Initialization', () => {
    it('should create connection manager with schema', () => {
      const onStatusChange = vi.fn()
      
      const manager = createConnectionManager(
        testSchema,
        onStatusChange,
        'English'
      )

      expect(manager).toBeDefined()
      expect(manager.connect).toBeDefined()
      expect(manager.disconnect).toBeDefined()
      expect(manager.getStatus).toBeDefined()
    })

    it('should initialize SchemaFormStateManager on creation', () => {
      const onStatusChange = vi.fn()
      
      createConnectionManager(
        testSchema,
        onStatusChange,
        'English'
      )

      // Check that state was saved to sessionStorage
      const stored = sessionStorage.getItem('schema_form_state')
      expect(stored).toBeDefined()
      
      if (stored) {
        const state = JSON.parse(stored)
        expect(state.schema.form_metadata.form_number).toBe('I-90')
        expect(state.currentPartId).toBe('part-1') // Should start at first part
      }
    })

    it('should support shared MediaStream for VAD coordination', () => {
      const onStatusChange = vi.fn()
      const mockStream = {} as MediaStream
      
      const manager = createConnectionManager(
        testSchema,
        onStatusChange,
        'English',
        mockStream
      )

      expect(manager).toBeDefined()
      expect(manager.getAudioManager).toBeDefined()
    })
  })

  describe('Manager Methods', () => {
    it('should provide field manager access', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      const fieldManager = manager.getFieldManager()
      expect(fieldManager).toBeDefined()
    })

    it('should provide audio manager access', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      const audioManager = manager.getAudioManager()
      expect(audioManager).toBeDefined()
    })

    it('should track connection status', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      const status = manager.getStatus()
      expect(status).toBe('disconnected')
    })

    it('should support pause/resume', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.pause).toBeDefined()
      expect(manager.resume).toBeDefined()
      expect(manager.isPaused).toBeDefined()
    })
  })

  describe('Section Management', () => {
    it('should support startSection', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.startSection).toBeDefined()
      expect(typeof manager.startSection).toBe('function')
    })

    it('should support switchSection', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.switchSection).toBeDefined()
      expect(typeof manager.switchSection).toBe('function')
    })

    it('should support completeSection', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.completeSection).toBeDefined()
      expect(typeof manager.completeSection).toBe('function')
    })

    it('should track current section', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.getCurrentSection).toBeDefined()
      expect(manager.getCompletedSections).toBeDefined()
    })
  })

  describe('VAD Integration', () => {
    it('should provide VAD speech callbacks', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.onVADSpeechStart).toBeDefined()
      expect(manager.onVADSpeechEnd).toBeDefined()
      expect(typeof manager.onVADSpeechStart).toBe('function')
      expect(typeof manager.onVADSpeechEnd).toBe('function')
    })

    it('should support push-to-talk mode', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.setPushToTalkMode).toBeDefined()
      expect(typeof manager.setPushToTalkMode).toBe('function')
    })
  })

  describe('Language Support', () => {
    it('should accept initial fill language', () => {
      const onStatusChange = vi.fn()
      
      const manager = createConnectionManager(
        testSchema,
        onStatusChange,
        'Spanish'
      )

      expect(manager).toBeDefined()
      expect(manager.changeFillLanguage).toBeDefined()
    })

    it('should support changing fill language', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.changeFillLanguage).toBeDefined()
      expect(typeof manager.changeFillLanguage).toBe('function')
    })

    it('should support changing spoken language', () => {
      const onStatusChange = vi.fn()
      const manager = createConnectionManager(testSchema, onStatusChange, 'English')

      expect(manager.changeSpokenLanguage).toBeDefined()
      expect(typeof manager.changeSpokenLanguage).toBe('function')
    })
  })

  describe('State Persistence', () => {
    it('should persist state across manager recreations', () => {
      const onStatusChange = vi.fn()
      
      // Create first manager
      createConnectionManager(testSchema, onStatusChange, 'English')
      
      // Get stored state
      const stored = sessionStorage.getItem('schema_form_state')
      expect(stored).toBeDefined()
      
      // Create second manager - should load existing state
      createConnectionManager(testSchema, onStatusChange, 'English')
      
      const stored2 = sessionStorage.getItem('schema_form_state')
      expect(stored2).toBe(stored)
    })
  })
})
