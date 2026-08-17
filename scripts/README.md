# Scripts Directory

Quick helper scripts for development and testing.

---

## 🏢 Firm Bootstrap (operator script)

### `bootstrap_firm.py`

Creates/updates a firm record (`firms/{firm_id}` in Firestore) and stamps the
`firm_id` + `firm_role` custom claims on the firm's staff Firebase accounts
(bd polyglot-pdf-lo88). The **script docstring** is the single source of truth
for usage, `--dry-run`, and the exit-code contract; the runnable admin step is
also documented in `docs/components/auth.md` ("Firm identity"). Requires an
explicit `--project` (only `polyglot-demo-aa709` is live) and runs under your
own gcloud ADC.

Sibling operator scripts `read_confirmations.py` and `read_kit_revision.py`
likewise document themselves in their module docstrings.

---

## 🚀 Backend Launcher

### Windows
```cmd
scripts\start_backend.bat
```

### Bash (Git Bash, WSL, Linux, Mac)
```bash
bash scripts/start_backend.sh
```

**What it does:**
- Activates virtual environment
- Checks/installs dependencies
- Starts backend on http://localhost:8000
- Shows API docs at http://localhost:8000/docs

---

## 🔧 Fix Virtual Environment (After Folder Rename)

**Problem:** Renamed folder from `PDF_voice_filler_2` to `web_form_voice_filler`?  
**Solution:** Virtual environment paths are now broken!

### Windows
```cmd
scripts\fix_venv.bat
```

### Bash
```bash
bash scripts/fix_venv.sh
```

**What it does:**
1. Removes old `.venv` folder
2. Creates fresh virtual environment
3. Installs all dependencies from `backend/requirements.txt`
4. Ready to use!

**Time:** ~2-3 minutes

---

## 📋 Other Scripts

### `dev_env.ps1` (PowerShell)
Full development environment setup (backend + frontend)

```powershell
.\scripts\dev_env.ps1
```

Options:
- `-BackendOnly`: Only start backend
- `-FrontendOnly`: Only start frontend

### `dev-local.ps1` (PowerShell)
The canonical local test stack (backend + frontend), wrapped by the `/run-local`
skill. See `docs/doctrine/promotion-tiers.md`.

---

## 📝 Quick Reference

| Task | Windows | Bash |
|------|---------|------|
| Local test stack | `.\scripts\dev-local.ps1` | `bash scripts/dev-local.sh` |
| Start backend | `scripts\start_backend.bat` | `bash scripts/start_backend.sh` |
| Fix venv | `scripts\fix_venv.bat` | `bash scripts/fix_venv.sh` |
| Full dev env | `.\scripts\dev_env.ps1` | N/A |

---

## 🐛 Troubleshooting

### "Virtual environment not found"
**Solution:** Run `fix_venv.bat` or `bash scripts/fix_venv.sh`

### "Module not found" errors
**Solution:** 
```bash
source .venv/Scripts/activate  # or .venv/bin/activate
pip install -r backend/requirements.txt
```

### "Port 8000 already in use"
**Solution:** 
```bash
# Find process using port 8000
netstat -ano | findstr :8000  # Windows
lsof -i :8000                  # Mac/Linux

# Kill the process or use different port
uvicorn backend.main:app --port 8001
```

### "Permission denied" on .sh files
**Solution:**
```bash
chmod +x scripts/*.sh
```

---

## 📚 Related Documentation

- **Backend Setup:** See `README.md` in root directory
- **Doc map:** See `docs/INDEX.md` (canonical); architecture overview in `CLAUDE.md`
