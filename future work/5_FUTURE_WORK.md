# Future Work

**Last Updated**: October 10, 2025  
**MVP Status**: Phase 2 COMPLETE ✅

---

## Optional Testing

- **Security**: XSS review, CSP compatibility
- **Performance**: 200+ field forms, audio latency profiling
- **Cross-Site**: Test on real-world forms, compatibility matrix

## Phase 3 Features (Deferred)

- **Advanced Fields**: Checkbox groups, file uploads, signatures
- **Multi-page navigation**
- **UX**: Waveform viz, transcript display, undo, history
- **Technical**: SPA auto-detection, multi-browser, Shadow DOM, code splitting
- **Analytics**: Connection logging, token tracking, metrics

---

**Why Deferred**: MVP complete, these are polish/edge-cases

## Post-MVP Features (Deferred)

### Advanced Navigation
- Hidden field handling
- Disabled field handling
- Conditional field visibility
- Field dependencies
- Section-based navigation
- Tab order awareness

### Complex Forms
- Multi-page forms (wizards)
- Date/time pickers
- WYSIWYG editors
- Custom web components

### Advanced Features
- Custom voice commands
- Form templates/presets
- Undo/redo
- Keyboard shortcuts
- A/B testing
- Advanced analytics

## Automatic SPA Navigation Detection
**Current (MVP)**: Manual "Rescan" button when form changes  
**Future**: MutationObserver with debouncing to auto-detect form changes
```typescript
const observer = new MutationObserver(debounce(() => {
  const currentFieldCount = scanFields().length;
  if (Math.abs(currentFieldCount - lastFieldCount) > 5) {
    showNotification("Form changed. Click 'Rescan' to update.");
  }
}, 1000));
```
**Why deferred**: Complex, prone to false positives, not needed for controlled demos

## Shadow DOM Exploration
**Current (MVP)**: Regular DOM with CSS namespacing  
**Future**: Investigate Shadow DOM with portal/slot for field indicators
- Better CSS isolation
- May require hybrid approach (Shadow for UI, regular for field access)

**Why deferred**: May not be viable given requirement to attach indicators to form fields

## Enhanced UI Features
**Current (MVP)**: Basic status display, connect/start/stop buttons  
**Future**:
- Audio waveform visualization
- Real-time transcript display
- Field-by-field confirmation UI with undo
- Latency metrics visualization
- Conversation history panel

## Intelligent Schema Merging
**Current (MVP)**: Full re-parse on "Rescan"  
**Future**: Smart merge of old/new schemas
- Preserve filled fields during re-parse
- Detect which fields were added/removed
- Maintain user edits across SPA navigation

## Accessibility Enhancements
**Current (MVP)**: Basic overlay functionality  
**Future**:
- Full ARIA labels on overlay
- Keyboard shortcuts (Ctrl+Shift+V to activate, etc.)
- Screen reader announcements for status changes
- High contrast mode support
- Focus management for keyboard-only users
