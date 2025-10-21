/**
 * Unit tests for WebFormConnection backend URL handling
 * 
 * Ensures the correct backend URL is used during:
 * 1. Initial connection
 * 2. Section switches (reconnects with new session)
 * 3. Section completion (reconnects to next section)
 * 
 * Critical for production: Deployed apps must NEVER fall back to localhost
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { WebFormConnection } from '../src/webFormConnection'
import type { FormSchema } from '../src/webFormState'

// Mock WebFormStateManager
const mockState = {
  session_id: 'test-session',
  current_section: 'section1',
  section_index: { section1: 0, section2: 1, section3: 2 },
  schema: {} as any,
  all_values: {},
  section_status: {},
}

vi.mock('../src/webFormState', () => ({
  WebFormStateManager: {
    init: vi.fn(() => mockState),
    load: vi.fn(() => mockState),
    updateSessionId: vi.fn(),
    saveSchema: vi.fn(),
    saveSectionIndex: vi.fn(),
    saveSectionStatus: vi.fn(),
  },
  FormSchema: {} as any,
}))

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState: number = WebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  
  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    
    // Simulate async connection
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 10)
  }
  
  send(data: string | ArrayBuffer) {
    // Track sent messages for verification
    MockWebSocket.sentMessages.push(data)
  }
  
  close() {
    this.readyState = WebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }
  
  // Helper to simulate receiving a message
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { 
        data: typeof data === 'string' ? data : JSON.stringify(data) 
      }))
    }
  }
  
  static sentMessages: any[] = []
  static reset() {
    MockWebSocket.instances = []
    MockWebSocket.sentMessages = []
  }
}

// Mock sessionStorage
const mockSessionStorage: Record<string, string> = {}
const sessionStorageMock = {
  getItem: (key: string) => mockSessionStorage[key] || null,
  setItem: (key: string, value: string) => { mockSessionStorage[key] = value },
  removeItem: (key: string) => { delete mockSessionStorage[key] },
  clear: () => { Object.keys(mockSessionStorage).forEach(key => delete mockSessionStorage[key]) },
  get length() { return Object.keys(mockSessionStorage).length },
  key: (index: number) => Object.keys(mockSessionStorage)[index] || null,
}

// Test schema with sections
const testSchema: FormSchema = {
  source: 'web',
  form_metadata: {
    title: 'Test Form',
    url: 'https://example.com/form',
  },
  fields: [
    { id: 'field1', name: 'Field 1', type: 'text' },
    { id: 'field2', name: 'Field 2', type: 'text' },
    { id: 'field3', name: 'Field 3', type: 'text' },
    { id: 'field4', name: 'Field 4', type: 'text' },
  ],
}

const testSectionIndex = {
  sections: [
    { section_number: 1, label: 'Section 1', field_ids: ['field1', 'field2'] },
    { section_number: 2, label: 'Section 2', field_ids: ['field3', 'field4'] },
  ],
  total_sections: 2,
}

describe('WebFormConnection - Backend URL Handling', () => {
  beforeEach(() => {
    // Setup mocks
    global.WebSocket = MockWebSocket as any
    global.sessionStorage = sessionStorageMock as any
    MockWebSocket.reset()
    sessionStorageMock.clear()
    
    // Clear any console logs
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })
  
  afterEach(() => {
    vi.restoreAllMocks()
  })
  
  describe('Initial Connection', () => {
    it('should connect to production URL when provided', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Connect with production URL
      await connection.connect(productionUrl, 1000)
      
      // Verify WebSocket was created with correct URL
      expect(MockWebSocket.instances.length).toBe(1)
      expect(MockWebSocket.instances[0].url).toBe(productionUrl)
    })
    
    it('should connect to localhost when provided (dev mode)', async () => {
      const localhostUrl = 'ws://localhost:8000/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Connect with localhost URL
      await connection.connect(localhostUrl, 1000)
      
      // Verify WebSocket was created with correct URL
      expect(MockWebSocket.instances.length).toBe(1)
      expect(MockWebSocket.instances[0].url).toBe(localhostUrl)
    })
    
    it('should store the connected URL for later use', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Connect
      await connection.connect(productionUrl, 1000)
      
      // Access private property for verification (TypeScript bypass)
      const connectedUrl = (connection as any).connectedUrl
      expect(connectedUrl).toBe(productionUrl)
    })
  })
  
  describe('Section Switching', () => {
    it('should use the same URL as initial connection when switching sections', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section index
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Initial connection
      await connection.connect(productionUrl, 1000)
      
      // Simulate session ready
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Clear instances to track new connection
      const firstConnectionUrl = MockWebSocket.instances[0].url
      MockWebSocket.instances = []
      
      // Switch to section 2 (should reconnect with same URL)
      await connection.switchSection(2, productionUrl)
      
      // Wait for reconnection
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // Verify new WebSocket was created with the SAME production URL
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
      const newConnectionUrl = MockWebSocket.instances[MockWebSocket.instances.length - 1].url
      expect(newConnectionUrl).toBe(productionUrl)
      expect(newConnectionUrl).toBe(firstConnectionUrl)
    })
    
    it('should NOT fall back to localhost when switching sections in production', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section index
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Initial connection to production
      await connection.connect(productionUrl, 1000)
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Switch to section 2
      await connection.switchSection(2, productionUrl)
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // Verify NO connection attempted to localhost
      const allUrls = MockWebSocket.instances.map(ws => ws.url)
      expect(allUrls.every(url => url === productionUrl)).toBe(true)
      expect(allUrls.some(url => url.includes('localhost'))).toBe(false)
    })
    
    it('should throw error if URL is not provided to switchSection', async () => {
      const connection = new WebFormConnection(testSchema)
      
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Attempt to switch section without URL (should throw)
      await expect(async () => {
        await (connection as any).switchSection(2, '')
      }).rejects.toThrow('wsUrl is required')
    })
  })
  
  describe('Section Completion', () => {
    it('should use the same URL when completing section and moving to next', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section index
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Initial connection
      await connection.connect(productionUrl, 1000)
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Clear instances to track new connection
      MockWebSocket.instances = []
      
      // Complete section (should reconnect to next section with same URL)
      await connection.completeSection(productionUrl)
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // Verify new WebSocket was created with production URL
      expect(MockWebSocket.instances.length).toBeGreaterThan(0)
      const newConnectionUrl = MockWebSocket.instances[MockWebSocket.instances.length - 1].url
      expect(newConnectionUrl).toBe(productionUrl)
      expect(newConnectionUrl).not.toContain('localhost')
    })
    
    it('should throw error if URL is not provided to completeSection', async () => {
      const connection = new WebFormConnection(testSchema)
      
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Attempt to complete section without URL (should throw)
      await expect(async () => {
        await (connection as any).completeSection('')
      }).rejects.toThrow('wsUrl is required')
    })
  })
  
  describe('Internal Message Handlers', () => {
    it('should use stored connectedUrl when AI requests section switch', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section index
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Initial connection
      await connection.connect(productionUrl, 1000)
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Clear instances to track new connection
      MockWebSocket.instances = []
      
      // Simulate AI requesting section switch via WebSocket message
      MockWebSocket.instances[0].simulateMessage({
        type: 'switch_section',
        identifier: '2',
      })
      
      // Wait for async handling
      await new Promise(resolve => setTimeout(resolve, 100))
      
      // Verify reconnection used production URL (from stored connectedUrl)
      if (MockWebSocket.instances.length > 0) {
        const reconnectUrl = MockWebSocket.instances[MockWebSocket.instances.length - 1].url
        expect(reconnectUrl).toBe(productionUrl)
        expect(reconnectUrl).not.toContain('localhost')
      }
    })
    
    it('should use stored connectedUrl when AI requests section completion', async () => {
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section index
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: {},
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Initial connection
      await connection.connect(productionUrl, 1000)
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Clear instances to track new connection
      MockWebSocket.instances = []
      
      // Simulate AI requesting section completion via WebSocket message
      MockWebSocket.instances[0].simulateMessage({
        type: 'complete_section',
      })
      
      // Wait for async handling
      await new Promise(resolve => setTimeout(resolve, 100))
      
      // Verify reconnection used production URL (from stored connectedUrl)
      if (MockWebSocket.instances.length > 0) {
        const reconnectUrl = MockWebSocket.instances[MockWebSocket.instances.length - 1].url
        expect(reconnectUrl).toBe(productionUrl)
        expect(reconnectUrl).not.toContain('localhost')
      }
    })
  })
  
  describe('Regression Test: Production Deployment Scenario', () => {
    it('should NEVER use localhost when deployed with production URL', async () => {
      // Simulate production deployment scenario
      const productionUrl = 'wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill'
      const connection = new WebFormConnection(testSchema)
      
      // Initialize with section-based form
      sessionStorageMock.setItem('vff_web_form_state', JSON.stringify({
        schema: testSchema,
        current_values: { field1: 'value1', field2: 'value2' },
        section_index: testSectionIndex,
        current_section: 1,
        completed_sections: [],
      }))
      
      // Step 1: Initial connection to production
      await connection.connect(productionUrl, 1000)
      MockWebSocket.instances[0].simulateMessage({
        type: 'session_ready',
        session_id: 'test-session-1',
      })
      
      // Step 2: Switch to section 2
      await connection.switchSection(2, productionUrl)
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // Step 3: Switch back to section 1
      await connection.switchSection(1, productionUrl)
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // Step 4: Complete section 1 (should move to section 2)
      await connection.completeSection(productionUrl)
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // CRITICAL VERIFICATION: All connections must be to production URL
      const allUrls = MockWebSocket.instances.map(ws => ws.url)
      
      console.log('All connection URLs:', allUrls)
      
      // Assert: NO localhost connections
      expect(allUrls.every(url => url === productionUrl)).toBe(true)
      expect(allUrls.some(url => url.includes('localhost'))).toBe(false)
      
      // Assert: All connections are to production
      allUrls.forEach(url => {
        expect(url).toBe(productionUrl)
      })
    })
  })
})
