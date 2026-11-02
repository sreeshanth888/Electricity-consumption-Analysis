import os
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

def db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "electricity_analysis"),
        port=int(os.getenv("DB_PORT", "3306")),
    )

def init_db():
    """Create the project database tables if they do not already exist."""
    # Database must exist first. Create it separately so the app user only needs
    # privileges on the project database for normal operation.
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        port=int(os.getenv("DB_PORT", "3306")),
    )
    try:
        cur = conn.cursor()
        db_name = os.getenv("DB_NAME", "electricity_analysis")
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        cur.execute(f"USE `{db_name}`")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS consumers (
                consumer_id INT AUTO_INCREMENT PRIMARY KEY,
                consumer_name VARCHAR(120) NOT NULL,
                consumer_type ENUM('Residential','Commercial','Industrial','Agricultural','Other') NOT NULL DEFAULT 'Residential',
                region VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meters (
                meter_id INT AUTO_INCREMENT PRIMARY KEY,
                consumer_id INT NOT NULL,
                meter_code VARCHAR(60) NOT NULL UNIQUE,
                installed_on DATE NULL,
                meter_status ENUM('Active','Inactive') NOT NULL DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_meter_consumer FOREIGN KEY (consumer_id)
                    REFERENCES consumers(consumer_id) ON DELETE RESTRICT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meter_readings (
                reading_id INT AUTO_INCREMENT PRIMARY KEY,
                meter_id INT NOT NULL,
                reading_date DATE NOT NULL,
                cumulative_kwh DECIMAL(12,3) NOT NULL,
                note VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_reading_meter FOREIGN KEY (meter_id)
                    REFERENCES meters(meter_id) ON DELETE RESTRICT,
                UNIQUE KEY uq_meter_reading_date (meter_id, reading_date),
                INDEX idx_reading_date (reading_date)
            )
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()

def query_all(sql, params=()):
    conn = db_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()

def execute(sql, params=()):
    conn = db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        last_id = cur.lastrowid
        cur.close()
        return last_id
    finally:
        conn.close()

def as_float(value):
    return float(value) if value is not None else 0.0

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/health")
def health():
    try:
        rows = query_all("SELECT DATABASE() AS db_name")
        return jsonify({"ok": True, "database": rows[0]["db_name"]})
    except Error as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

@app.get("/api/overview")
def overview():
    summary = query_all("""
        SELECT
          (SELECT COUNT(*) FROM consumers) AS consumers,
          (SELECT COUNT(*) FROM meters WHERE meter_status='Active') AS active_meters,
          (SELECT COUNT(*) FROM meter_readings) AS readings
    """)[0]
    period = query_all("""
        SELECT COALESCE(SUM(usage_kwh),0) AS monthly_kwh
        FROM (
          SELECT r.meter_id, r.reading_date,
                 r.cumulative_kwh - LAG(r.cumulative_kwh) OVER
                    (PARTITION BY r.meter_id ORDER BY r.reading_date) AS usage_kwh
          FROM meter_readings r
          WHERE r.reading_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
        ) x
        WHERE usage_kwh >= 0
    """)[0]
    return jsonify({**summary, "monthly_kwh": as_float(period["monthly_kwh"])})

@app.get("/api/consumers")
def consumers():
    rows = query_all("""
        SELECT c.consumer_id, c.consumer_name, c.consumer_type, c.region,
               COUNT(DISTINCT m.meter_id) AS meter_count
        FROM consumers c LEFT JOIN meters m ON m.consumer_id=c.consumer_id
        GROUP BY c.consumer_id ORDER BY c.consumer_id DESC
    """)
    return jsonify(rows)

@app.post("/api/consumers")
def add_consumer():
    data = request.get_json(silent=True) or {}
    name = (data.get("consumer_name") or "").strip()
    region = (data.get("region") or "").strip()
    kind = data.get("consumer_type") or "Residential"
    allowed = {"Residential", "Commercial", "Industrial", "Agricultural", "Other"}
    if not name or not region or kind not in allowed:
        return jsonify({"error": "Consumer name, region, and a valid consumer type are required."}), 400
    try:
        cid = execute(
            "INSERT INTO consumers (consumer_name, consumer_type, region) VALUES (%s,%s,%s)",
            (name, kind, region)
        )
        return jsonify({"message": "Consumer created.", "consumer_id": cid}), 201
    except Error as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/meters")
def meters():
    rows = query_all("""
        SELECT m.meter_id, m.consumer_id, m.meter_code, m.installed_on,
               m.meter_status, c.consumer_name, c.region
        FROM meters m JOIN consumers c ON c.consumer_id=m.consumer_id
        ORDER BY m.meter_id DESC
    """)
    return jsonify(rows)

@app.post("/api/meters")
def add_meter():
    data = request.get_json(silent=True) or {}
    try:
        cid = int(data.get("consumer_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a consumer."}), 400
    code = (data.get("meter_code") or "").strip()
    installed = data.get("installed_on") or None
    if not code:
        return jsonify({"error": "Meter code is required."}), 400
    try:
        meter_id = execute(
            "INSERT INTO meters (consumer_id, meter_code, installed_on) VALUES (%s,%s,%s)",
            (cid, code, installed)
        )
        return jsonify({"message": "Meter created.", "meter_id": meter_id}), 201
    except Error as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/api/readings")
def readings():
    rows = query_all("""
        SELECT r.reading_id, r.meter_id, m.meter_code, c.consumer_name,
               r.reading_date, r.cumulative_kwh, r.note
        FROM meter_readings r
        JOIN meters m ON m.meter_id=r.meter_id
        JOIN consumers c ON c.consumer_id=m.consumer_id
        ORDER BY r.reading_date DESC, r.reading_id DESC
        LIMIT 500
    """)
    for row in rows:
        row["cumulative_kwh"] = as_float(row["cumulative_kwh"])
        row["reading_date"] = str(row["reading_date"])
    return jsonify(rows)

@app.post("/api/readings")
def add_reading():
    data = request.get_json(silent=True) or {}
    try:
        meter_id = int(data.get("meter_id"))
        reading_date = date.fromisoformat(data.get("reading_date", ""))
        value = Decimal(str(data.get("cumulative_kwh", "")))
    except (TypeError, ValueError, ArithmeticError):
        return jsonify({"error": "Meter, valid date, and numeric cumulative kWh are required."}), 400
    if not value.is_finite() or value < 0:
        return jsonify({"error": "Cumulative kWh must be a non-negative number."}), 400

    previous = query_all("""
        SELECT reading_date, cumulative_kwh FROM meter_readings
        WHERE meter_id=%s AND reading_date < %s
        ORDER BY reading_date DESC LIMIT 1
    """, (meter_id, reading_date))
    following = query_all("""
        SELECT reading_date, cumulative_kwh FROM meter_readings
        WHERE meter_id=%s AND reading_date > %s
        ORDER BY reading_date ASC LIMIT 1
    """, (meter_id, reading_date))
    # A cumulative register should not decrease. A decrease may indicate reset,
    # rollover, or a data-entry error, so flag it instead of silently accepting it.
    if previous and value < Decimal(str(previous[0]["cumulative_kwh"])):
        return jsonify({"error": "Reading is lower than the previous cumulative reading. Check for a reset/rollover; this reading was not saved."}), 400
    if following and value > Decimal(str(following[0]["cumulative_kwh"])):
        return jsonify({"error": "Reading is higher than the next cumulative reading. Check chronology or a reset/rollover; this reading was not saved."}), 400
    try:
        rid = execute("""
            INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh, note)
            VALUES (%s,%s,%s,%s)
        """, (meter_id, reading_date, value, (data.get("note") or "").strip() or None))
        return jsonify({"message": "Reading saved.", "reading_id": rid}), 201
    except Error as exc:
        return jsonify({"error": "Could not save reading. Check that this meter does not already have a reading on that date. " + str(exc)}), 400

@app.get("/api/report")
def report():
    period = request.args.get("period", "month")
    start = request.args.get("start")
    end = request.args.get("end")
    threshold = request.args.get("threshold", "500")
    try:
        threshold = float(threshold)
        if threshold < 0:
            raise ValueError()
    except ValueError:
        return jsonify({"error": "Threshold must be a non-negative number of kWh."}), 400
    if period not in ("month", "year", "range"):
        period = "month"

    # LAG is supported by MySQL 8+. We calculate consecutive differences first,
    # then aggregate by the date of the later reading.
    where = []
    params = []
    if period == "month":
        where.append("r.reading_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')")
        where.append("r.reading_date < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)")
    elif period == "year":
        where.append("r.reading_date >= MAKEDATE(YEAR(CURDATE()),1)")
        where.append("r.reading_date < MAKEDATE(YEAR(CURDATE())+1,1)")
    else:
        if start:
            where.append("r.reading_date >= %s"); params.append(start)
        if end:
            where.append("r.reading_date <= %s"); params.append(end)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = query_all(f"""
        WITH diffs AS (
          SELECT r.meter_id, r.reading_date,
                 r.cumulative_kwh,
                 LAG(r.cumulative_kwh) OVER (PARTITION BY r.meter_id ORDER BY r.reading_date) AS previous_kwh,
                 LAG(r.reading_date) OVER (PARTITION BY r.meter_id ORDER BY r.reading_date) AS previous_date
          FROM meter_readings r
        ),
        valid_usage AS (
          SELECT d.meter_id, d.reading_date,
                 (d.cumulative_kwh-d.previous_kwh) AS usage_kwh
          FROM diffs d
          WHERE d.previous_kwh IS NOT NULL
            AND d.cumulative_kwh >= d.previous_kwh
        )
        SELECT DATE_FORMAT(v.reading_date, %s) AS period_label,
               c.consumer_id, c.consumer_name, c.consumer_type, c.region,
               m.meter_id, m.meter_code, SUM(v.usage_kwh) AS usage_kwh
        FROM valid_usage v
        JOIN meters m ON m.meter_id=v.meter_id
        JOIN consumers c ON c.consumer_id=m.consumer_id
        WHERE v.reading_date >= COALESCE((SELECT MIN(reading_date) FROM meter_readings), '1000-01-01')
        {("AND " + " AND ".join(where).replace("r.reading_date", "v.reading_date")) if where else ""}
        GROUP BY period_label, c.consumer_id, c.consumer_name, c.consumer_type, c.region, m.meter_id, m.meter_code
        ORDER BY period_label DESC, usage_kwh DESC
    """, ({"month": "%Y-%m", "year": "%Y", "range": "%Y-%m"}[period], *params))
    # The reading-validation report scans every chronological pair, including resets.
    validation = query_all("""
        SELECT m.meter_code, c.consumer_name, a.reading_date AS earlier_date,
               b.reading_date AS later_date, a.cumulative_kwh AS earlier_kwh,
               b.cumulative_kwh AS later_kwh
        FROM meter_readings a
        JOIN meter_readings b ON b.meter_id=a.meter_id AND b.reading_date > a.reading_date
        JOIN meters m ON m.meter_id=a.meter_id
        JOIN consumers c ON c.consumer_id=m.consumer_id
        WHERE b.reading_date = (
          SELECT MIN(x.reading_date) FROM meter_readings x
          WHERE x.meter_id=a.meter_id AND x.reading_date>a.reading_date
        ) AND b.cumulative_kwh < a.cumulative_kwh
        ORDER BY b.reading_date DESC
    """)
    cleaned = []
    for row in rows:
        row["usage_kwh"] = as_float(row["usage_kwh"])
        cleaned.append(row)
    high = [r for r in cleaned if r["usage_kwh"] > threshold]
    totals = {}
    for r in cleaned:
        label = r["period_label"]
        totals[label] = totals.get(label, 0) + r["usage_kwh"]
    trend = [{"period": k, "usage_kwh": round(v, 3)} for k, v in sorted(totals.items())]
    return jsonify({
        "period": period, "threshold_kwh": threshold, "rows": cleaned,
        "high_usage": high, "trend": trend,
        "validation": [{
            "meter_code": x["meter_code"], "consumer_name": x["consumer_name"],
            "earlier_date": str(x["earlier_date"]), "later_date": str(x["later_date"]),
            "earlier_kwh": as_float(x["earlier_kwh"]), "later_kwh": as_float(x["later_kwh"]),
            "issue": "Cumulative reading decreased — possible reset, rollover, or entry error"
        } for x in validation]
    })

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "An unexpected server error occurred. Check the Flask terminal for details."}), 500

if __name__ == "__main__":
    try:
        init_db()
        print("Database tables are ready.")
    except Error as exc:
        print("Database setup failed:", exc)
        print("Check .env credentials and ensure MySQL Server is running.")
        raise
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
