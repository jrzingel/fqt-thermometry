# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FQT Thermometry is a centralized monitoring and alerting system for Bluefors dilution refrigerators used by the Morello FQT group at UNSW. It provides a Flask web dashboard, a REST API, an alert system that sends Microsoft Teams notifications, and a listener application deployed on each fridge PC to capture and upload log data.

## Commands

### Dependencies
Package manager is `uv`. Install from https://docs.astral.sh/uv/.
```bash
uv sync
```

### Running
```bash
uv run website          # Web server only
uv run alerts           # Alert system only
uv run all              # Both simultaneously (production)
```

### Database Setup
Requires PostgreSQL with TimescaleDB extension.
```bash
sudo -u postgres psql -c "CREATE DATABASE thermometry"
uv run -- flask --app thermometry.flaskr init-db
uv run -- flask --app thermometry.flaskr create-default-fridges
uv run -- flask --app thermometry.flaskr add-fridge <name>
uv run -- flask --app thermometry.flaskr add-sensor <name> <fridge_id> <0|1>
uv run -- flask --app thermometry.flaskr create-dummy-data   # test data
```

### Building Executables
```bash
uv run build-listener    # Listener .exe for fridge PCs
uv run build-watchdog    # Watchdog .exe for website monitoring
```

### No Test Suite
There is no formal test suite. Use `create-dummy-data` for manual testing.

## Architecture

The system has four independently deployed components:

1. **Web Server + API** (`src/thermometry/flaskr/`) — Flask/APIFlask app served via Waitress. `api.py` handles REST endpoints under `/api/v1/`, `dashboard.py` serves the HTML UI under `/dashboard/`. `db.py` manages PostgreSQL/TimescaleDB connections and CLI commands. The database uses a dual-table strategy: `measurement` (hypertable for history) and `latest_reading` (most recent per sensor).

2. **Alert System** (`src/thermometry/alarm/`) — `Watchtower.py` orchestrates scheduled checks every 30 seconds. Individual alert classes in `alerts/` inherit from `Alert.py` which implements a state machine (DISABLED → ENABLED → ALARM → MANUALLY_DISABLED). Alerts send Teams messages via webhook.

3. **Listener** (`src/listener/`) — Deployed as a PyInstaller executable on each fridge PC. `listener.py` watches BlueFors log files, parses multiple log formats, and uploads readings to the central API with HMAC-SHA256 signatures. Configured via `fridge.yaml`.

4. **Watchdog** (`src/watchdog/`) — Standalone executable that pings the website and alerts via Teams if it's down.

Entry point `src/thermometry/main.py` spawns the web server and alert system as separate processes.

## Configuration

Two config files are required (not committed to git):
- `src/thermometry/config.py` — Database credentials, HMAC keys, Teams webhooks, server settings (copy from `config.example.py`)
- `src/thermometry/config.yaml` — Maps alert types to fridges (copy from `config.example.yaml`)

Listener requires `fridge.yaml` alongside the executable (example at `src/listener/fridge.yaml`).

## Key Technical Details

- **API authentication**: Listener uploads are validated with HMAC-SHA256 signatures; each fridge has a unique secret key in `config.py`
- **Database**: TimescaleDB hypertable with 1-week chunks, auto-compression after 2 months
- **Frontend**: Jinja2 templates + vanilla JavaScript with uPlot.js for charts, Tailwind CSS for styling
- **Python**: Requires >=3.12
