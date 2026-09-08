# ECDAT Backend - FastAPI CBOM Scanner

## Setup Instructions

### 1. Create and activate a virtual environment

```bash
python -m venv test_virt_env
source test_virt_env/bin/activate
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode along with all development dependencies:
- `fastapi`, `uvicorn[standard]` for the web server
- `sqlalchemy>=2`, `alembic` for ORM and migrations
- `psycopg[binary]`, `redis` for Postgres and Redis support
- `python-multipart` for multipart request handling
- `pytest`, `httpx` for testing

### 3. Initialize the database and run migrations

```bash
alembic upgrade head
```

This applies the initial migration creating the following tables:
- `scan_runs` - scan job tracking (id, target, source_type, status, created_at, completed_at, files_scanned, error_message)
- `detection_rows` - detected cryptographic artefacts (id, scan_id FK, file_path, line_number, matched_text, asset_type, algorithm_family, key_size_bits, quantum_vulnerable, classically_broken, confidence, language, detection_method)
- `risk_assessments` - Mosca's inequality risk assessments (id, detection_id FK unique, migration_time_years, shelf_life_years, threat_horizon_years, urgency_ratio, risk_level, mosca_violation)
- `recommendations` - PQC migration recommendations (id, detection_id FK unique, recommended_algorithm, fips_reference, rationale, latency_note, migration_note)

### 4. Start the development server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000/health`.

### 5. Run the health check test

```bash
python -m pytest backend/tests/test_health.py -v
```

### 6. Run the full test suite

```bash
python -m pytest --tb=short
```

## Project Structure

```
backend/
  pyproject.toml          # Package configuration with FastAPI dependencies
  app/
    __init__.py           # Package init
    main.py               # FastAPI app instance, GET /health endpoint
    db.py                 # SQLAlchemy 2.0 engine/session setup
    models_orm.py         # SQLAlchemy 2.0 ORM models
  alembic/
    env.py                # Alembic environment configuration
    versions/
      initial.py          # Initial migration schema
  migrations/             # Legacy migrations directory (deprecated, use alembic/versions/)
  tests/
    test_health.py       # Health endpoint pytest test
```

## API Endpoints

- `GET /health` - Returns `{"status": "ok"}` with HTTP 200