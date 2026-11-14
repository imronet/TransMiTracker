# TransMiTracker

A local-first Windows desktop application for exploring TransMilenio/SITP
journeys in Bogotá, built with Python, CustomTkinter, SQLite and GTFS data.

## Why this project?

Planning a commute requires more than a published timetable. TransMiTracker aims
to help people decide when to leave home and understand their return journey,
using defensible historical evidence and, eventually, operational data.

That recommendation is a future goal. Today's application configures journeys,
queries scheduled services and provides an experimental offline GPS engine.

## Current status

**Version 0.3.0 — Experimental offline route tracker delivered.** The application
and documentation are under active development. The interface and most technical
documents are in Spanish.

Start with the [offline route tracker guide](docs/getting-started/OFFLINE_ROUTE_TRACKER.md)
for the manual PowerShell command. It uses saved snapshots and a local catalog;
it does not collect live positions. See the
[v0.3.0 delivery report](docs/archive/phases/PHASE3B_ROUTE_TRACKER_REPORT.md)
for the saved real example and its historical validation (106 relevant tests).
The conservative engine's earlier synthetic evaluation remains in the
[Phase 3A report](docs/archive/phases/PHASE3A_REPORT.md).

## Available today

- [Manual offline route tracker](docs/getting-started/OFFLINE_ROUTE_TRACKER.md)
  for saved GPS sessions: candidate vehicle segments and route geometry progress,
  without requiring an exact static trip or stable `start_time`.
- Local GTFS catalog import and searches for stops, routes and stop patterns.
- Downstream destination selection with platform and stop-occurrence identities.
- Home → Work and Work → Home profiles with one to three legs.
- Drafts, revision checks and profiles pinned to their catalog version.
- Optional scheduled-service queries, including service calendars and midnight.
- User-defined walking allowances and warnings for unverified transfers.
- Experimental offline GPS replay with provenance, conservative identity checks,
  trajectory segmentation, estimated crossings and uncertainty intervals.
- Separate SQLite stores for the static catalog, profiles and GPS evidence.
- [Local GPS pilot preparation](docs/getting-started/LOCAL_GPS_PILOT.md): manual
  tooling and offline analysis. One
  [bounded real session](docs/archive/phases/PHASE3B_FIRST_REAL_REPORT.md)
  completed; its permission is consumed. Another capture requires a new conditions
  review and separate execution approval. No second session is authorized.

## Planned, not active

Shared snapshot collection, independently verified operational identities,
historical journey recommendations, arrival predictions and Telegram notifications
remain future work. Further collection or implementation requires explicit approval.
There is no mobile app or deployed backend.
Croma is an optional future integration; the current application does not require
an account, key or credits from that provider.

## Requirements and installation

- Windows x64; the validated environment uses **Python 3.13.14** and Tk 8.6.
- The project declares Python 3.12+, but other versions have not been validated.
- A local static GTFS catalog is required for journey selection. Downloaded feeds
  and local databases are excluded from Git and are not bundled with a checkout.

From the repository root in PowerShell:

```powershell
py -3.13 -m venv .venv
$env:PIP_CACHE_DIR = Join-Path (Get-Location).Path '.cache\pip'
$env:TEMP = Join-Path (Get-Location).Path '.cache\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

`requirements-lock.txt` pins the validated environment. Runtime dependencies are
listed in `requirements.txt`; development tools in `requirements-dev.txt`.
No virtual-environment activation or PowerShell execution-policy change is needed.

## Quick start

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'src'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m transmitracker.gui
```

If the catalog is absent, use the [setup guide](docs/getting-started/SETUP.md)
to import a ZIP you have obtained locally. The GUI remains navigable without it,
but cannot configure catalog-backed journeys.

Choose a profile, select a route/pattern and stop occurrences, then save.
Configured journeys do not require an example date or departure time.
See the [Spanish user guide](docs/getting-started/USAGE.md) for drafts, transfers,
optional schedule queries and privacy details.

An explicit synthetic diagnostic works without a downloaded feed:

```powershell
.\.venv\Scripts\python.exe -m transmitracker --offline --output data/offline-diagnostic.json
```

## Documentation and roadmap

Start with the [documentation index](docs/INDEX.md).

- [Current offline route tracker and PowerShell command](docs/getting-started/OFFLINE_ROUTE_TRACKER.md)
- [Setup and catalog import](docs/getting-started/SETUP.md)
- [Architecture and data boundaries](docs/architecture/OVERVIEW.md)
- [Offline replay and development commands](docs/development/VALIDATION.md)
- [Implementation plan and authorization history](docs/development/IMPLEMENTATION_PLAN.md)
- [Versioning](docs/development/VERSIONING.md)
- [Optional future provider and credit-budget design](docs/research/CROMA_INTEGRATION_DESIGN.md)
- [Historical reports and evidence](docs/archive/evidence/INDEX.md)

## Important limitations

Static GTFS times are scheduled services, not live arrivals. Realtime identifiers
do not always match the static catalog. A candidate identity is not a verified
operational identity, and an estimated crossing is not an observed arrival.

Synthetic accuracy does not establish real-world accuracy. The isolated saved
GPS capture validates parsing and references, not travel times or vehicle speeds.
There is no continuous tracking, validated ETA, active Croma integration,
Telegram delivery or production scheduler. Opening a profile starts none of these.

Profiles and preferences stay locally under `data/gui/`. Optional secrets belong
only in `.env`, which is excluded from Git but **is not encrypted**. Never commit
credentials, personal profiles, downloaded feeds or local databases.

## AI assistance and contributions

The project is developed with AI assistance under human supervision. Changes
require human review; AI-generated results are not independent operational proof.
Contributors should read [AGENTS.md](AGENTS.md) and the
[documentation policy](docs/development/DOCUMENTATION_POLICY.md), preserve
architectural contracts and distinguish implemented features from future work.

No project license file is currently present. This README does not grant a
license or imply that upstream GTFS/provider data share a single license.
