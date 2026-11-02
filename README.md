# Electricity Consumption Analysis System

A full-stack local web application for managing electricity consumers, meters, and cumulative meter readings, then analyzing usage by month/year or a custom date range.

## Stack
- Frontend: HTML, CSS, JavaScript, Chart.js
- Backend: Python + Flask REST endpoints
- Database: MySQL 8.0+ (uses window functions such as `LAG`)
- Units: cumulative meter register and calculated usage are in **kWh**

## Features
- Dashboard cards for consumers, active meters, monthly usage, and saved readings
- Add consumer, meter, and dated cumulative reading records
- Validates duplicate meter/date readings, negative values, and cumulative readings that decrease relative to neighboring readings
- Monthly, yearly, and custom-range reports
- Configurable high-usage threshold
- Usage trend chart, consumer/meter comparison, high-usage list, and reading-validation report
- Responsive layout for desktop and mobile

## 1. Prerequisites
Install Python 3.10+ and MySQL Server 8.0+. Start the MySQL service.

## 2. Setup
Open a terminal in this project directory:

```bash
python -m venv .venv
```

Activate it:

**Windows PowerShell**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**
```bat
.venv\Scripts\activate.bat
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

Install packages:

```bash
pip install -r requirements.txt
```

Review `.env` and ensure its MySQL username/password match your local server. The app creates the `electricity_analysis` database and tables on startup. The MySQL account needs permission to create the database and tables. For safer deployment, create a dedicated MySQL user with privileges only on this project database instead of using `root`.

## 3. Run
```bash
python app.py
```
Open http://127.0.0.1:5000 in your browser.

## 4. Recommended sample workflow
1. Add a consumer (for example, "Sample Home", Residential, Hyderabad).
2. Add a meter (for example, "HYD-1001") linked to that consumer.
3. Add at least two readings for that meter on different dates:
   - 2026-01-01 — 1200 kWh
   - 2026-02-01 — 1380 kWh
4. The calculated consumption between these readings is 180 kWh. The usage is attributed to the date of the later reading.
5. Choose Month, Year, or Custom range and set a high-usage threshold such as 500 kWh.

## Calculation assumptions and limitations
- `cumulative_kwh` is the cumulative register value shown by the meter, not the consumption for that day/month.
- Consumption between consecutive valid readings = later cumulative kWh − earlier cumulative kWh.
- A pair is considered valid only when the later cumulative reading is greater than or equal to the earlier reading.
- A decrease may indicate a meter reset, rollover, replacement, or typing error. This application flags decreases; it does **not** automatically infer rollover values or modify readings.
- The period label is based on the later reading date. This is an analytical grouping, not an official utility billing calculation.
- The current report uses MySQL 8.0+ window functions. The monthly dashboard card totals usage from readings dated in the current month; it is only an estimate based on available readings.
- High usage means a calculated usage value strictly greater than the configured threshold. Threshold is a project setting, not a utility standard.
- This project is a development starter. Before production use, add authentication/authorization, CSRF protection, audit logging, backups, migrations, monitoring, and a dedicated least-privilege database account.

## Database entities
- `consumers(consumer_id, consumer_name, consumer_type, region)`
- `meters(meter_id, consumer_id, meter_code, installed_on, meter_status)`
- `meter_readings(reading_id, meter_id, reading_date, cumulative_kwh, note)`

## API endpoints
- `GET /api/health`
- `GET/POST /api/consumers`
- `GET/POST /api/meters`
- `GET/POST /api/readings`
- `GET /api/overview`
- `GET /api/report?period=month|year|range&threshold=500&start=2026-01-01&end=2026-12-31`

## Important security note
`.env` contains a database password and is excluded by `.gitignore`. Do not upload it to GitHub, share it publicly, or use the root account in a deployed production system. If this password has been used outside your private local setup, rotate it.
