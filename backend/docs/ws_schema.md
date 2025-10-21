# WebSocket schema and message contracts

This document describes the WebSocket message shapes used by the backend (`/echo`, `/audio`, `/fill`). A machine-readable JSON Schema is available at `ws_schema.json`.

## High-level rules

- All JSON messages MUST include a `type` string describing the message intent.

- Binary frames (audio chunks, file bytes) are sent as raw binary frames. When sending binary frames, clients SHOULD precede them with a small JSON control frame that includes `type` and `session_id` so the server knows how to interpret the next binary frame.

## Common message shapes

### Ping / Echo

Example:

```json
{
  "type": "ping",
  "id": "uuid",
  "payload": { /* optional */ }
}
```

### Session control

Example:

```json
{
  "type": "start_session",  // or "close_session", "get_status"
  "session_id": "optional-client-provided-or-empty",
  "metadata": { /* ... */ }
}
```

### Audio chunk (recommended usage)

1. Send a JSON frame:

```json
{
  "type": "audio_chunk",
  "session_id": "abc",
  "seq": 42,
  "encoding": "pcm16-16k",
  "samples_ms": 20
}
```

2. Immediately send the raw binary audio frame (the bytes matching `encoding`).

### Tool call / Tool response

From client:

```json
{
  "type": "tool_call",
  "session_id": "abc",
  "tool": "update_pdf_form_fields",
  "call_id": "call-1",
  "arguments": { /* ... */ }  // or string
}
```

From server:

```json
{
  "type": "tool_response",
  "session_id": "abc",
  "tool": "update_pdf_form_fields",
  "call_id": "call-1",
  "response": { /* ... */ }
}
```

### Form update (structured)

```json
{
  "type": "form_update",
  "session_id": "abc",
  "updates": [ { "field_id": "FullName", "value": "Alice" }, /* ... */ ]
}
```

## Notes for implementers

- Tests should mock or stub the receive/send loops; use small helper functions that send the JSON control frame, then the binary payload when exercising audio paths.

- The schema is intentionally permissive for `arguments` and `response` fields; adapters may accept either JSON objects or escaped JSON strings depending on upstream SDK behavior.

## Examples

- Sending an audio chunk (JavaScript WebSocket):

```js
ws.send(JSON.stringify({type: 'audio_chunk', session_id: 's1', seq: 1, encoding: 'pcm16-16k'}));
// then send binary Float32/Int16/whatever depending on encoding
ws.send(audioArrayBuffer);
```

Frontend and tests should rely on these contracts and avoid multiplexing ad-hoc shapes.
