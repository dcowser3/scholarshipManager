# Athletic Scholarship Management System

Phase 1 foundation for a University of Toledo athletic scholarship workflow replacement.

## Stack

- Backend: FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite
- Auth: email/password with Argon2 and signed session cookie
- Documents: scaffolded storage and import seams; generation lands in later phases
- Cohort recovery: blank or `TGN` cohorts can be assigned manually by sport and are reused on future imports

## Getting Started

1. Start the stack:

```bash
docker compose up --build
```

2. In another shell, run migrations:

```bash
cd backend
uv sync
uv run alembic upgrade head
```

3. Seed baseline data:

```bash
cd backend
uv run python -m app.scripts.seed
```

4. Optionally import the real CSV:

```bash
cd backend
uv run python -m app.scripts.import_csv "/Users/deriancowser/Downloads/Athletic Aid Amounts (1).csv" --user-email admin@utoledo.edu
```

## Default Accounts

- `admin@utoledo.edu` / `ChangeMe123!`
- `football.coach@utoledo.edu` / `ChangeMe123!`
- `softball.coach@utoledo.edu` / `ChangeMe123!`

## Notes

- The live CSV currently has 426 data rows and 28 duplicate Rocket IDs.
- The current CSV importable row count is 425 data rows once the trailing blank line is ignored.
- The importer reads the file with `utf-8-sig`, drops duplicate IDs with last-row-wins semantics, and records that count in `import_runs`.
- The real file also contains 21 blank cohorts and many `TGN` cohorts. Those now land in a sport-scoped pending queue, where a coach or admin can assign the right academic year once and have the importer remember it.
- Sport `display_name` values are seeded conservatively for now so the unresolved naming questions can be confirmed without schema churn.
