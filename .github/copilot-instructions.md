### Order Tracker — AI contributor guidance

This repository is a small Flask web app (single process) backed by SQLite. The goal of this file is to provide concise, actionable notes for an AI coding agent to be productive immediately.

- Key facts
- Entrypoint: `app.py` — a single Flask app configured to use `SQLite` via `Flask-SQLAlchemy` (database file: `database.db` created next to `app.py`).
- Templates: HTML templates live in `templates/` and follow basic Jinja2 usage (see `index.html`, `orders.html`, `add_order.html`, `edit_order.html`).
- Static assets: `static/style.css` only; keep changes minimal and follow existing Bootstrap 5 usage.
- Tests: `test_app.py` and `test_db.py` use `unittest` and an in-memory SQLite DB. Tests are run directly with `python test_app.py`.
- Docker: `Dockerfile` and `docker-compose.yml` provide a simple way to run the app in a container. The container runs `python app.py` and exposes port 5000.

Big-picture architecture
- Single-process Flask app (no blueprint splitting). Data model is in `app.py`: two SQLAlchemy models — `Order` and `LineItem`. Orders have many LineItems via `order.items`.
- Routes are defined in `app.py` and handle both HTML rendering and form processing. There is no REST API; changes should preserve server-rendered HTML patterns unless tests or README indicate otherwise.
- Persistence: SQLite file `database.db` by default. Tests override this to `sqlite:///:memory:`.

Project-specific conventions and patterns
- Database model placement: models are declared in `app.py`. When editing models, update `db.create_all()` usage in the `__main__` block if you add migrations (this project currently has no migration system like Alembic).
- Date handling: `Order.date_ordered` uses `datetime.utcnow()` default. When adding logic that depends on time, use UTC-aware comparisons similar to the `view_orders` overdue logic.
- Form fields: multi-value inputs use `product[]` and `quantity[]` (see `add_order` and `edit_order`). Keep the same name patterns when adding form-backed features.
- Deleting/Updating LineItems: `edit_order` deletes existing LineItems via `LineItem.query.filter_by(order_id=order.id).delete()` then re-inserts from the form; mirror that flow for compatible behavior.

- Developer workflows (commands)
- Prerequisites (recommended before running tests or the app):
  - Use Python 3.11+ if available. Create and activate a virtual environment and install dependencies:

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # macOS/Linux (zsh)
    pip install -r requirements.txt
    ```

  - If `python` on your machine maps to Python 2, use `python3` for the commands above and when running tests.

- Local dev (venv):
  - Create venv: `python -m venv venv` then `source venv/bin/activate` (macOS/Linux)
  - Install: `pip install -r requirements.txt`
  - Run app: `python app.py` — creates `database.db` automatically and starts Flask on 0.0.0.0:5000 in debug mode.
- Tests:
  - Run unit tests: `python test_app.py` (tests create an in-memory DB; safe to run locally)
- Docker:
  - Build: `docker build -t order-tracker .`
  - Run: `docker run -p 5000:5000 order-tracker` or use `docker-compose up --build`

Integration points and external dependencies
- No external services; primary dependencies are declared in `requirements.txt` (Flask, Flask-SQLAlchemy, SQLAlchemy). The app assumes local file storage for the SQLite DB.
- GitHub Actions: README references a test workflow badge. Keep unit tests fast and self-contained.

Guidance for code changes (concise rules)
- Preserve server-side rendering: modify templates in `templates/` and route handlers in `app.py` together.
- When changing models:
  - Update `app.py` model classes.
  - Tests rely on `db.create_all()` in an app context; ensure `with app.app_context(): db.create_all()` remains usable.
  - Do not add migrations without notifying maintainers.
- Form handling:
  - Use `request.form.getlist('product[]')` pattern for multi-value fields.
  - Validate numeric fields with int() and fallback as seen in `add_order`.
- Avoid adding background workers or async complexity; keep changes synchronous unless adding tests and Docker updates.

Examples to reference
- Overdue logic: `view_orders()` marks orders overdue if Pending and older than 7 days — replicate same style for derived flags.
- Adding line items: `add_order()` commits the Order first, then iterates `product[]`/`quantity[]`, inserting `LineItem` objects and committing again.

Files to check when editing
- `app.py` (routes, models, DB init)
- `templates/*.html` (views)
- `static/style.css` (styling tweaks)
- `test_app.py`, `test_db.py` (tests to update if behavior changes)
- `requirements.txt` (add new deps here)

If you make a change that updates behavior or data schema
- Run `python test_app.py` locally and ensure all tests pass.
- Keep the `database.db` file creation behavior intact for local dev unless adding migrations.

Alembic (schema migrations)
- This project now includes Alembic scaffolding in `alembic/` and `alembic.ini` configured to use the local `database.db`.
- Preferred workflow for schema changes:
  1. Update SQLAlchemy models in `app.py`.
  2. Generate an autogenerate migration locally:

    ```bash
    ./venv/bin/alembic revision --autogenerate -m "describe change"
    ```

  3. Inspect and edit the generated migration under `alembic/versions/` — autogenerate is a best-effort and often needs manual fixes.
  4. Apply the migration locally:

    ```bash
    ./venv/bin/alembic upgrade head
    ```

  Note: For initial development you may still use `db.create_all()`, but for any production or persisted DBs prefer Alembic migrations. Back up `database.db` before applying migrations on non-test environments.

When in doubt, ask the user for these missing project facts
- Should new models use Alembic migrations or simple `db.create_all()`?
- Preferred policy for semantic changes to templates vs API endpoints?

If you edit this file, keep it short (20-50 lines) and focused on immediate developer knowledge.

---
Please review this draft and tell me any missing assumptions or preferred conventions to include.
