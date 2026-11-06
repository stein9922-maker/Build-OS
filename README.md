# Build OS (MVP, Stage 2 of 4)

A local, beginner-friendly web app for construction scheduling and material procurement.
Stack: Python, Streamlit, SQLite, pandas, NetworkX, Plotly.

**Current status: Stage 2 - CPM scheduling and Gantt chart.** You can create projects, add
activities with durations, link them with finish-to-start dependencies (circular dependencies
are refused), and the **Schedule** tab calculates ES, EF, LS, LF, total float, the critical path
and the projected completion date, with an interactive Gantt chart. Procurement arrives in
Stages 3-4.

## Version-one assumptions (explicit on purpose)

- Durations are **whole calendar days**. No working calendars, weekends or holidays.
- A duration of **0** is allowed and means a milestone.
- All dependencies are **finish-to-start**, with **no lag or lead**.
- Activity codes are unique per project and stored in upper case (`a100` becomes `A100`).
- **Finish-exclusive dates.** Day 0 is the project start date. `EF = ES + duration`, so an
  activity occupies days `ES` to `EF - 1`, and EF is the first day *after* it - the day a
  successor may start. Example: start Mon 2 Nov, 5 days -> works Nov 2-6, EF = Sat Nov 7. The
  projected completion date (`start + project duration`) is finish-exclusive too.
- Activities with **no successor** may finish as late as the project end, so a short, disconnected
  activity shows positive float; a standalone chain as long as the project is critical.
- **Critical** means total float is exactly 0. If several equal-length zero-float chains exist the
  app reports how many and highlights every critical activity.
- The schedule is **calculated on demand and never stored**, so it cannot go stale and no database
  change was needed for Stage 2.
- The app never places orders and never invents quantities. Sample data contains no materials.

## Setup (Python 3.10+)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the tests

```bash
python -m unittest discover -v   # nothing extra to install; run from the project folder
# or, if you installed pytest:   pip install -r requirements-dev.txt && pytest
```

## Run the app

```bash
streamlit run app.py
```

Then click **Load demo project** in the sidebar and open the **Schedule** tab.
If the app is already running from an earlier stage, stop it (Ctrl+C) and start it again so
the new code is loaded. The database is created automatically at
`data/buildos.db` (set the `BUILDOS_DB_PATH` environment variable to move it).
To load the demo without the UI: `python -m buildos.sample_data`.

Some tests use stand-ins for Streamlit and Plotly (`tests/fakes.py`) so UI and chart code can run
without a browser. They prove our code runs and passes the right values, not how a page looks.
Two tests that exercise the *real* Plotly are skipped automatically when Plotly is not installed.

## Layout

| Path | Responsibility |
|---|---|
| `buildos/` | Core logic. **Never imports Streamlit.** |
| `buildos/validation.py` | Pure input checks and cleaning |
| `buildos/scheduling/graph.py` | NetworkX helpers: cycle detection |
| `buildos/scheduling/cpm.py` | CPM engine: forward/backward pass, float, critical path (pure logic) |
| `buildos/gantt.py` | Gantt data preparation (tested) and the Plotly figure |
| `buildos/db.py`, `repository.py` | SQLite connection, versioned schema, SQL queries |
| `buildos/services.py` | Business rules; one transaction per action; read-only `ScheduleService` |
| `buildos/sample_data.py` | Illustrative demo project |
| `webui/`, `app.py` | Thin Streamlit screens: collect input, call services, show results |
| `tests/` | Automated tests (each uses its own temporary database) |

## Roadmap

1. **Stage 1 (done):** projects, activities, FS dependencies, validation, cycle detection, SQLite, sample data, tests.
2. **Stage 2 (done):** CPM forward/backward pass (ES, EF, LS, LF, total float, critical path, completion date) and an interactive Plotly Gantt on the Schedule tab.
3. **Stage 3:** materials linked to activities, inventory, suppliers and lead times, purchase orders (records only).
4. **Stage 4:** order-by dates and procurement risk alerts, plus polish.


## Stage 3: Material procurement

The Procurement tab adds project-scoped material catalogues, activity-linked material requirements,
inventory (physical and reserved stock), suppliers and supplier lead times, purchase-order tracking,
and a deterministic procurement overview.

- Material need dates are derived from the existing CPM earliest-start dates; schedule changes are reflected on recalculation.
- Net purchase quantity = required quantity minus usable stock and eligible incoming quantity, never below zero.
- Only Ordered and Partially delivered orders expected by the need date count as incoming.
- Recommended order date = need date minus supplier lead time minus a 2-calendar-day buffer.
- The overview uses the earliest scheduled start among activities using each material, so it is a planning aid rather than a detailed phased material take-off.
- Quantities are only comparable when the material uses one consistent unit. Validate estimates, supplier terms, and quantities before making real purchases.
- Existing databases are upgraded with SQLite migration 2 on app startup; migration 1 is not edited.


## Stage 3.1 procurement improvements

- Purchase orders can now be edited (material, supplier, ordered/received quantities, dates, status and notes).
- Supplier quotations can be recorded by material, with quote date and validity date, then compared using estimated total cost for the project's recorded requirement.
- Procurement reports can be viewed and downloaded as CSV or Excel: material requirements, inventory, purchase orders, supplier quotations and procurement coverage.
- A new SQLite migration creates the `supplier_quotes` table automatically on startup. Existing database records are preserved; back up the database before upgrading.
- Quoted prices are user-entered estimates, not live market prices. Confirm specifications, GST, freight, minimum quantities and quote validity before placing real orders.

### Upgrade

1. Back up your existing `data/buildos.db` and project folder.
2. Replace the application source files with this release (do not replace your database with an empty one).
3. Install requirements with `python -m pip install -r requirements.txt`.
4. Run `python -m streamlit run app.py`. The database migration is applied automatically at startup.
