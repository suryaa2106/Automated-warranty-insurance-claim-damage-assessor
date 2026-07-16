# ClaimSnap — Automated Warranty/Insurance Claim Damage Assessor

A multi-agent pipeline that takes a live vehicle-damage photo and returns a
fraud-checked, cost-estimated, policy-validated claim decision with a
human-readable explanation.

## Architecture

```
Frontend (Vercel)              Backend (Render, FastAPI)
┌────────────────┐             ┌─────────────────────────────────────┐
│ index.html      │  POST img  │ main.py → orchestrator.py            │
│ app.js (camera, │ ─────────► │   1. vision_agent.py   (Gemini)      │
│  canvas prep)   │            │   2. fraud_agent.py    (EXIF+phash)  │
│ styles.css      │            │   3. cost_agent.py     (lookup table)│
└────────────────┘             │   4. policy_agent.py   (Supabase)    │
                                │   5. decision_agent.py (rules)       │
                                │   6. explanation_agent.py (Gemini)   │
                                └─────────────────────────────────────┘
                                              │
                                        Supabase (Postgres)
```

## Local setup (backend)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Optional — the app runs with mocks if these are unset:
export GEMINI_API_KEY="your-key-here"
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_KEY="your-service-role-or-anon-key"

uvicorn main:app --reload --port 8000
```

Without `GEMINI_API_KEY`, `vision_agent.py` and `explanation_agent.py` fall
back to deterministic mock output. Without `SUPABASE_URL`/`SUPABASE_KEY`,
`policy_agent.py` uses two built-in demo policies (`POLICY-DEMO-001`,
`POLICY-DEMO-002`) and `orchestrator.py` stores claims in memory. This means
**the app runs fully end-to-end with zero configuration.**

## Local setup (frontend)

The frontend is static — just open `frontend/index.html` in a browser, or
serve it:

```bash
cd frontend
python -m http.server 5500
```

By default `app.js` points at `http://localhost:8000`. To point at a deployed
backend, set `window.CLAIM_API_BASE_URL` before `app.js` loads, e.g. add this
in `index.html` right above the `<script src="app.js">` tag:

```html
<script>window.CLAIM_API_BASE_URL = "https://your-backend.onrender.com";</script>
```

## Supabase schema (optional)

If you want real persistence instead of the mock fallback, create these
tables in Supabase:

```sql
create table policies (
  policy_id text primary key,
  active boolean default true,
  deductible integer,
  coverage_cap integer,
  covered_categories text[],
  policy_type text
);

create table claims (
  claim_id text primary key,
  submitted_at timestamptz,
  user_name text,
  vehicle_reg_number text,
  insurance_type text,
  policy_id text,
  vision_result jsonb,
  fraud_result jsonb,
  cost_result jsonb,
  policy_result jsonb,
  decision_result jsonb,
  summary_text text
);
```

## Deployment

- **Backend → Render**: New Web Service, root dir `backend/`, build command
  `pip install -r requirements.txt`, start command
  `uvicorn main:app --host 0.0.0.0 --port $PORT`. Add `GEMINI_API_KEY`,
  `SUPABASE_URL`, `SUPABASE_KEY` as environment variables.
- **Frontend → Vercel**: root dir `frontend/`, no build step needed (static
  HTML/JS/CSS). Set `window.CLAIM_API_BASE_URL` to your Render URL as shown
  above.

## Demo flow

1. Log in with name, vehicle reg number, insurance type, and a policy ID
   (`POLICY-DEMO-001` = Comprehensive, `POLICY-DEMO-002` = Basic Liability).
2. Tap "Tap to open camera" — this opens the device's native back camera
   directly (gallery picker is bypassed via `capture="environment"`).
3. The captured photo is auto-oriented and lightly sharpened/contrast-boosted
   on an HTML5 canvas before upload.
4. Submit — the backend runs all six agents and returns a claim ID, decision
   status, itemized cost breakdown, fraud signal summary, and a plain-English
   explanation.

## Known limitations (be upfront about these in Q&A)

- Cost estimation uses a hardcoded lookup table, not a real parts/labor
  pricing API.
- The duplicate-image fraud check compares against a small mocked hash
  array, not a real claims history table.
- `capture="environment"` reliably forces the native camera on most mobile
  browsers, but desktop browsers will fall back to a file picker since
  there's no camera hardware to prefer.
