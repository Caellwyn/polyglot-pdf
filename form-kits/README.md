# Form Kits

Each folder in this directory represents a complete PDF/schema pair that the schema-form demo can render.

## Folder layout

```text
form-kits/
  <form-id>/
    schema.json      # required. schema exported from backend extractor
    form.pdf         # required. source PDF that receives filled data
    metadata.json    # optional. overrides defaults such as label/description
```

- `<form-id>` doubles as the stable identifier surfaced in the UI drop-down. Keep it URL-safe.
- If `metadata.json` is missing, the UI derives a friendly label from `<form-id>` (e.g., `i-90` → `I 90`).
- `metadata.json` shape:

```json
{
  "label": "I-90 (Replace Permanent Resident Card)",
  "description": "USCIS Form I-90, latest edition",
  "schema": "schema.json", // optional if not using a custom filename
  "pdf": "form.pdf"        // optional if not using a custom filename
}
```

Add a new form by dropping the schema + PDF (and optional metadata) into its own folder, then run `npm run form-kits:prepare` from `frontend/` (this command is also hooked into dev/build/test/preview/npm install lifecycles).
