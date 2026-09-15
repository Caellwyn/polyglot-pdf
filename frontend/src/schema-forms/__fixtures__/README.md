# Test fixtures

`w7_sections_frozen.json` is a MECHANICAL PROJECTION of the shipped W-7 kit's
`schema.json` (source, sha256 and copy date are inside the file under `_source`):
the section ids and each section's field-id list, which is exactly what
`applyResume.ts` reads. It exists because no form kit lives in git any more
(PR #780) while `applyResume.test.ts` deliberately tests against the REAL
shipped schema shape, not an invented one. The test prefers the live
`form-kits/w7/schema.json` when a checkout has one and falls back to this
projection (CI). Nothing under `frontend/src` is ever uploaded to the kits bucket.

Refresh after the W-7 kit changes (writes this file from the bucket copy):

```bash
gcloud storage cp gs://polyglot-demo-aa709-form-kits/form-kits/w7/schema.json /tmp/w7.schema.json
python - <<'EOF'
import json, hashlib, pathlib
raw = pathlib.Path('/tmp/w7.schema.json').read_bytes(); d = json.loads(raw)
p = pathlib.Path('frontend/src/schema-forms/__fixtures__/w7_sections_frozen.json'); cur = json.loads(p.read_text())
cur['_source']['sha256'] = hashlib.sha256(raw).hexdigest(); cur['sections'] = [{'id': s['id'], 'fields': list(s.get('fields', []))} for s in d['sections']]
p.write_text(json.dumps(cur, indent=2) + '
')
EOF
```
