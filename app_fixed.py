from flask import Flask, jsonify, send_file, request
import paramiko
from generate_health_excel import (
    SSH_PORT,
    SSH_PASSWORD,
    SSH_HOST, SSH_USERNAME,SAT_USERNAME,SAT_HOST,SAT_PASSWORD,
    run_linux_command,
    run_sat_commands,
    parse_df_output,
    parse_alarms_output,
)

from yesterday_peak import run_yesterday_peak
from list_trunk_group import run_list_trunk_group, parse_list_trunk_group
from monitor_traffic_trunk_groups import run_monitor_traffic_trunk_groups, parse_monitor_traffic_output

# ---- add these imports near the other script imports ----
from status_trunk import run_status_trunk_all, run_status_trunk, parse_status_trunk

import csv

import re

from flask_cors import CORS
import os, time, glob, sqlite3
from datetime import datetime
import pandas as pd
from generate_health_excel import generate_health_data

import subprocess
from flask import jsonify

# allow frontend to download Excel directly
from flask import send_from_directory

from yesterday_peak import run_avaya_command, parse_trunk_summary
from yesterday_peak import run_avaya_command, parse_trunk_summary, COMMAND

import json



import json
CREDS_FILE = ".creds.json"

def save_creds(ip, password):
    try:
        with open(CREDS_FILE, "w") as f:
            json.dump({"ip": ip, "password": password}, f)
    except:
        pass

def load_creds():
    try:
        with open(CREDS_FILE, "r") as f:
            return json.load(f)
    except:
        return None

from flask_cors import CORS
import os, time, glob, sqlite3
from datetime import datetime
import pandas as pd
from generate_health_excel import generate_health_data

import subprocess
from flask import jsonify

# allow frontend to download Excel directly
from flask import send_from_directory

from yesterday_peak import run_avaya_command, parse_trunk_summary
from yesterday_peak import run_avaya_command, parse_trunk_summary, COMMAND

import json

# ======================================================
# Flask App Setup
# ======================================================
app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
EXCEL_PATH = os.path.join(BASE_DIR, "latest_avaya_page_log.xlsx")

os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

EXCEL_DIR = os.path.join(BASE_DIR, "reports")

# === yesterday-peak integration ===
PY_SCRIPT = os.path.join(BASE_DIR, "yesterday_peak.py")
FILE_PATTERN = "list_measurements_trunk-group_summary_yesterday-peak_*.xlsx"



# === list trunk-group integration ===
LIST_TRUNK_SCRIPT = os.path.join(BASE_DIR, "list_trunk_group.py")
LIST_TRUNK_PATTERN = "list_trunk-group_*.xlsx"


# === monitor traffic trunk-groups integration ===
MONITOR_SCRIPT = os.path.join(BASE_DIR, "monitor_traffic_trunk-groups.py")
MONITOR_PATTERN = "monitor_traffic_trunk-groups_*.xlsx"


DB_PATH = os.path.join(BASE_DIR, "command_logs.db")

_cached_health_data = None
_cached_timestamp = None


# ======================================================
# DB Logging (used by trunk modules)
# ======================================================
def init_command_log_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command_name TEXT,
            executed_at TEXT,
            status TEXT,
            excel_path TEXT,
            output_summary TEXT,
            duration REAL
        )
    """)
    conn.commit()
    conn.close()


def log_command(command_name, status, excel_path=None, output_summary=None, duration=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO command_logs (command_name, executed_at, status, excel_path, output_summary, duration)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (command_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          status, excel_path, output_summary, duration))
    conn.commit()
    conn.close()


# initialize DB when the app starts
init_command_log_db()



# ---- Command logs endpoint (GET) ----
@app.route("/get-command-logs", methods=["GET"])
def get_command_logs():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, command_name, executed_at, status, excel_path, output_summary, duration
            FROM command_logs
            ORDER BY id DESC
            LIMIT 500
        """)
        rows = c.fetchall()
        conn.close()

        logs = []
        for r in rows:
            logs.append({
                "id": r[0],
                "command_name": r[1],
                "executed_at": r[2],
                "status": r[3],
                "excel_path": r[4],
                "output_summary": r[5],
                "duration": r[6],
            })

        return jsonify({"logs": logs})
    except Exception as e:
        print("❌ Failed to fetch command logs:", e)
        return jsonify({"error": str(e)}), 500



# ======================================================
# Health Data Endpoints
# ======================================================
@app.route("/get-live-health-data", methods=["GET", "POST"])
def get_live_health_data():
    global _cached_health_data, _cached_timestamp

    try:
        # =======================
        # POST → Real-time fetch
        # =======================
        if request.method == "POST":
            data = request.get_json(force=True)

            ip = data.get("ip")
            password = data.get("password")

            print("📥 Received POST from UI:", ip, password)

            if not ip or not password:
                return jsonify({"error": "Missing IP or password"}), 400

            print(f"🔄 Fetching live data dynamically from {ip} ...")

            result = generate_health_data(ip=ip, password=password)

            if request.method == "POST":
                ip = data.get("ip")
                password = data.get("password")

                # avoid duplicate POST if React strict mode runs twice
                if _cached_timestamp and (datetime.now() - datetime.fromisoformat(_cached_timestamp)).total_seconds() < 2:
                    print("⏭️ Duplicate POST ignored (React strict mode)")
                    return jsonify(_cached_health_data)


            # Log commands
            try:
                logs = result.get("command_logs", [])
                for cl in logs:
                    command_name = cl.get("command")
                    status = cl.get("status", "Executed")
                    summary = cl.get("summary", "")
                    duration = float(cl.get("duration", 0.0))
                    log_command(command_name, status, excel_path=None,
                                output_summary=summary, duration=duration)
                print(f"✅ Logged {len(logs)} command(s) to command_logs.db")
            except Exception as e:
                print(f"⚠️ Failed to store command logs: {e}")

            # Cache for GET fallback
            _cached_health_data = result
            _cached_timestamp = datetime.now().isoformat()

            return jsonify(result)        # ⭐️ CRITICAL: STOP HERE

        # =======================
        # GET → Use cached/saved creds
        # =======================
        print("🟡 GET fallback using creds:", load_creds())

        creds = load_creds()
        if creds:
            result = generate_health_data(ip=creds["ip"],
                                          password=creds["password"])
        else:
            result = generate_health_data(ip="0.0.0.0", password="")

        _cached_health_data = result
        _cached_timestamp = datetime.now().isoformat()

        return jsonify(result)

    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        if _cached_health_data:
            return jsonify(_cached_health_data)
        return jsonify({"error": str(e)}), 500



# ---------------------------
# Helper - run a single linux command via SSH
# ---------------------------
def run_single_linux_command(cmd, ip, password, timeout=15):
    """Connect via SSH, run a single command and return (out, err)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, port=SSH_PORT, username=SSH_USERNAME, password=password, timeout=10)
        out, err = run_linux_command(client, cmd, timeout=timeout)
        return out, err
    finally:
        try:
            client.close()
        except Exception:
            pass

# ---------------------------
# Helper - run a single SAT command (re-uses run_sat_commands on a single command)
# ---------------------------
def run_single_sat_command(ip, password, cmd, timeout=10):
    try:
        return run_sat_commands(ip, SAT_PORT, SAT_USERNAME, password, [cmd], timeout_per_cmd=timeout).get(cmd, "")
    except Exception as e:
        return f"SAT error: {e}"

# ---------------------------
# Small endpoints: uptime, disk, server-status, alarms, backup
# Each accepts POST { ip, password } and also supports GET fallback to saved creds
# ---------------------------

def _get_creds_from_request_or_saved():
    """Helper to return (ip, password) from JSON POST or saved creds or None."""
    if request.method == "POST":
        try:
            j = request.get_json(force=True)
            ip = j.get("ip")
            password = j.get("password")
            if ip and password:
                # optional: persist for GET fallback
                save_creds(ip, password)
                return ip, password
        except Exception:
            pass
    c = load_creds()
    if c:
        return c.get("ip"), c.get("password")
    return None, None

@app.route("/health/uptime", methods=["GET", "POST"])
def health_uptime():
    ip, password = _get_creds_from_request_or_saved()
    if not ip or not password:
        return jsonify({"error": "Missing ip/password"}), 400
    try:
        out, err = run_single_linux_command("uptime", ip, password)
        # keep parsing same as before
        m = re.search(r"up\s+(\d+)\s+day", out)
        system_uptime = (m.group(1) + " days") if m else out.strip()
        return jsonify({"system_uptime": system_uptime, "raw": out, "error": err, "command": "uptime"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health/disk", methods=["GET", "POST"])
def health_disk():
    """
    Returns df -h and df -k parsed. Use GET fallback if needed.
    Optional query param 'which=df -h' or 'which=df -k' (defaults: both).
    """
    ip, password = _get_creds_from_request_or_saved()
    if not ip or not password:
        return jsonify({"error": "Missing ip/password"}), 400
    which = request.args.get("which", "").strip()
    response = {}
    try:
        if which in ("df -h", "df -k"):
            out, err = run_single_linux_command(which, ip, password)
            parsed = parse_df_output(out)
            response[which] = parsed
        else:
            out_h, err_h = run_single_linux_command("df -h", ip, password)
            out_k, err_k = run_single_linux_command("df -k", ip, password)
            response["df -h"] = parse_df_output(out_h)
            response["df -k"] = parse_df_output(out_k)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health/server-status", methods=["GET", "POST"])
def health_server_status():
    ip, password = _get_creds_from_request_or_saved()
    if not ip or not password:
        return jsonify({"error": "Missing ip/password"}), 400
    try:
        out, err = run_single_linux_command("/opt/ecs/bin/statusserver", ip, password)
        return jsonify({"server_status": out, "error": err})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health/alarms", methods=["GET", "POST"])
def health_alarms():
    ip, password = _get_creds_from_request_or_saved()
    if not ip or not password:
        return jsonify({"error": "Missing ip/password"}), 400
    try:
        out, err = run_single_linux_command("/opt/ecs/bin/almdisplay -v", ip, password)
        parsed = parse_alarms_output(out)
        return jsonify({"alarms_raw": out, "alarms_parsed": parsed, "error": err})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health/backup", methods=["GET", "POST"])
def health_backup():
    ip, password = _get_creds_from_request_or_saved()
    if not ip or not password:
        return jsonify({"error": "Missing ip/password"}), 400
    try:
        out, err = run_single_linux_command("/opt/ecs/sbin/backup -t", ip, password, timeout=30)
        return jsonify({"backup_status": out, "error": err})
    except Exception as e:
        return jsonify({"error": str(e)}), 500














@app.route("/download-health-excel", methods=["GET"])
def download_health_excel():
    try:
        if not os.path.exists(EXCEL_PATH):
            return jsonify({"error": "Excel not found"}), 404
        return send_file(EXCEL_PATH,
                         as_attachment=True,
                         download_name=os.path.basename(EXCEL_PATH),
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.route("/get-alarms-data", methods=["GET"])
def get_alarms_data():
    try:
        data = generate_health_data()  # or however you call almdisplay
        alarms_raw = data.get("alarms", "")
        parsed = parse_alarms_output(alarms_raw)
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.route("/reports/<path:filename>")
def download_report(filename):
    return send_from_directory(REPORT_DIR, filename, as_attachment=True)






# Endpoint to download a previously created excel file by filename
@app.route("/download-excel/<filename>", methods=["GET"])
def download_any_excel(filename):
    try:
        # Be safe: only allow files inside REPORT_DIR
        candidate = os.path.join(REPORT_DIR, filename)
        if not os.path.exists(candidate):
            return jsonify({"error": "File not found"}), 404
        return send_file(candidate, as_attachment=True, download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        print("[Backend] download-any-excel error:", e)
        return jsonify({"error": str(e)}), 500




def get_latest_trunk_excel():
    files = glob.glob(os.path.join(EXCEL_DIR, LIST_TRUNK_PATTERN))
    if not files:
        print("[Backend] No list_trunk-group Excel found.")
        return None
    latest = max(files, key=os.path.getmtime)
    print(f"[Backend] Latest list_trunk-group Excel: {latest}")
    return latest

# @app.route("/run-list-trunk-group", methods=["POST"])
# def run_list_trunk_group():
#     """Run list_trunk_group.py and wait for the new Excel file."""
#     try:
#         before_latest = get_latest_trunk_excel()
#         before_time = os.path.getmtime(before_latest) if before_latest else 0

#         print(f"[Backend] Running: {LIST_TRUNK_SCRIPT}")
#         subprocess.run(["python3", LIST_TRUNK_SCRIPT], check=True)

#         timeout = 30
#         start = time.time()
#         new_file = None
#         while time.time() - start < timeout:
#             latest = get_latest_trunk_excel()
#             if latest and (not before_latest or os.path.getmtime(latest) > before_time):
#                 new_file = latest
#                 break
#             time.sleep(1)

#         if not new_file:
#             msg = "[Backend] ❌ No new Excel file created for list trunk-group!"
#             print(msg)
#             return jsonify({"error": msg}), 500


#          # after you found new_file and before returning success
#         duration = round(time.time() - start, 2)  # if you have start_time stored
#         log_command("list-trunk-group", "Success", new_file, "Excel created", duration)

#         print(f"[Backend] ✅ New Excel ready: {new_file}")
#         return jsonify({"success": True, "excel_path": new_file})
#     except subprocess.CalledProcessError as e:
#         return jsonify({"error": f"Script failed: {str(e)}"}), 500
#     except Exception as e:
#         log_command("list-trunk-group", "Failed", None, str(e), 0)

#         return jsonify({"error": str(e)}), 500



@app.route("/get-list-trunk-group-data", methods=[ "POST"])
def get_list_trunk_group_data():
    """
    Run 'list trunk-group',
    parse output in memory, and return JSON + Excel path.
    """
    try:
        start_time = time.time()

        # EXACT SAME PATTERN AS YESTERDAY PEAK
        if request.method == "POST":
            req = request.get_json(force=True)
        else:
            req = request.args

        ip = req.get("ip")
        password = req.get("password")

        # If GET, just return an empty response so UI does not break


        # POST → execute command
        output = run_list_trunk_group(ip, password)

        if not output or output.strip() == "":
            return jsonify({"error": "Empty output from SAT command"}), 500

        df = parse_list_trunk_group(output)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = "list_trunk-group"
        excel_file = os.path.join(REPORT_DIR, f"{safe_prefix}_{timestamp}.xlsx")
        df.to_excel(excel_file, index=False)

        data_json = json.loads(df.to_json(orient="records"))
        columns = df.columns.tolist()
        duration = round(time.time() - start_time, 2)

        log_command(
            "list trunk-group",
            "success",
            excel_file,
            f"{len(df)} rows",
            duration
        )

        return jsonify({
            "data": data_json,
            "columns": columns,
            "excel_path": excel_file
        })

    except Exception as e:
        print(f"❌ Error in /get-list-trunk-group-data: {e}")
        return jsonify({"error": str(e)}), 500





HARDCODE_CSV = os.path.join(REPORT_DIR, "report_list_trunk-group.csv")

@app.route("/get-list-trunk-group-fixed", methods=["GET", "POST", "OPTIONS"])
def get_list_trunk_group_fixed():
    """
    Serve a cleaned JSON version of report_list_trunk-group.csv.
    Detects and removes leading title/meta rows and finds the real header row
    (looks for 'Group Number' or similar). Returns:
      { "columns": [...], "data": [...], "excel_path": "<csv path>" }
    """
    if request.method == "OPTIONS":
        return ("", 200)

    try:
        if not os.path.exists(HARDCODE_CSV):
            return jsonify({"error": "CSV not found", "path": HARDCODE_CSV}), 404

        # Read raw CSV into list of rows (preserve empty strings)
        with open(HARDCODE_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            raw_rows = [row for row in reader]

        # Normalize rows: strip each cell
        rows = [[(cell or "").strip() for cell in r] for r in raw_rows if any((cell or "").strip() for cell in r)]

        if not rows:
            return jsonify({"columns": [], "data": [], "excel_path": HARDCODE_CSV}), 200

        # Heuristics:
        # - First row frequently is a title like "12-3-2025 ... Report for Voice System .. - list trunk-group"
        # - Real header row often contains 'Group Number' or 'Group No' or 'Queue Length' etc.
        header_idx = None
        header_candidates = ["group number", "group no", "grp no", "queue length", "queue len", "group"]
        for i, r in enumerate(rows):
            joined = " ".join([c.lower() for c in r if c])
            if any(tok in joined for tok in header_candidates):
                header_idx = i
                break

        # If we couldn't find a header row, fallback:
        if header_idx is None:
            # try second row (common)
            header_idx = 1 if len(rows) > 1 else 0

        header_row = rows[header_idx]
        # If header row is a single very long title, try next row as header
        if len([c for c in header_row if c]) == 1 and header_idx + 1 < len(rows):
            # consider next row a true header
            header_idx += 1
            header_row = rows[header_idx]

        # Build columns by taking non-empty header cells and normalizing names
        columns = []
        for c in header_row:
            if c:
                name = c
            else:
                # generate placeholder column name if a blank cell exists in header
                name = f"col_{len(columns)+1}"
            # normalize name spacing
            name = " ".join(name.split())
            columns.append(name)

        # Data rows are rows after header_idx
        data_rows = []
        for r in rows[header_idx + 1:]:
            # pad/truncate row to match header length
            padded = (r + [""] * len(columns))[:len(columns)]
            # make object mapping header->value
            obj = {columns[i]: padded[i] for i in range(len(columns))}
            data_rows.append(obj)

        # If it looks like the CSV had vertical layout (labels in first column, values in second),
        # convert it to one-row keyed object.
        # Example pattern in your sample: header_row had "Group Number:" in column 2 and "Queue Length:" in column 1.
        # Detect if header contains a big title (single long string) and the following rows look like pairs.
        if len(columns) == 1 and len(data_rows) > 0:
            # try transposing label/value pairs into tabular rows
            # build list of pairs from remaining rows where first cell is label-like
            pairs = []
            for r in rows[header_idx + 1:]:
                # if row length >=2 and either cell contains ":" or small text
                if len(r) >= 2 and (r[0] or r[1]):
                    label = r[0].rstrip(":").strip() or f"col_1"
                    value = r[1].strip()
                    pairs.append((label, value))
            if pairs:
                # create columns from labels and a single row from values
                derived_columns = [p[0] for p in pairs]
                derived_row = {p[0]: p[1] for p in pairs}
                columns = derived_columns
                data_rows = [derived_row]

        return jsonify({
            "columns": columns,
            "data": data_rows,
            "excel_path": HARDCODE_CSV
        }), 200

    except Exception as e:
        app.logger.exception("Failed to parse hardcoded list trunk-group CSV")
        return jsonify({"error": str(e)}), 500

















# @app.route("/get-list-trunk-group-data", methods=["GET"])
# def get_list_trunk_group_data():
#     try:
#         latest = get_latest_trunk_excel()
#         if not latest:
#             return jsonify({"error": "No list_trunk-group Excel found"}), 404
#         df = pd.read_excel(latest)
#         return df.to_json(orient="records")
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

@app.route("/download-list-trunk-group", methods=["GET"])
def download_list_trunk_group():
    try:
        latest = get_latest_trunk_excel()
        if not latest:
            return jsonify({"error": "No Excel file found"}), 404
        return send_file(
            latest,
            as_attachment=True,
            download_name=os.path.basename(latest),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500






def get_latest_excel():
    """Return latest Excel file path."""
    files = glob.glob(os.path.join(EXCEL_DIR, FILE_PATTERN))
    if not files:
        print("[Backend] No Excel files found in reports directory.")
        return None
    latest = max(files, key=os.path.getmtime)
    print(f"[Backend] Latest Excel file found: {latest}")
    return latest


@app.route("/download-excel/<filename>", methods=["GET"])
def download_excel(filename):
    path = os.path.join(REPORT_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True)





# @app.route("/run-yesterday-peak", methods=["POST"])
# def run_yesterday_peak():
#     """Run the Python script and wait for new Excel."""
#     try:
#         before_latest = get_latest_excel()
#         before_time = os.path.getmtime(before_latest) if before_latest else 0

#         print(f"[Backend] Running: {PY_SCRIPT}")
#         subprocess.run(["python3", PY_SCRIPT], check=True)

#         # Wait for a new file
#         timeout = 30
#         start = time.time()
#         new_file = None
#         while time.time() - start < timeout:
#             latest = get_latest_excel()
#             if latest and (not before_latest or os.path.getmtime(latest) > before_time):
#                 new_file = latest
#                 break
#             time.sleep(1)

#         if not new_file:
#             msg = "[Backend] ❌ No new Excel file created after running script!"
#             print(msg)
#             return jsonify({"error": msg}), 500

#         # after you found new_file and before returning success
#         duration = round(time.time() - start, 2)  # if you have start_time stored
#         log_command("list measurements trunk-group summary yesterday-peak", "Success", new_file, "Excel created", duration)


#         print(f"[Backend] ✅ New Excel file ready: {new_file}")
#         return jsonify({"success": True, "excel_path": new_file})
#     except subprocess.CalledProcessError as e:
#         print("[Backend] ❌ Script execution failed:", e)
#         return jsonify({"error": f"Script failed: {str(e)}"}), 500
#     except Exception as e:
#         print("[Backend] ❌ Exception:", e)
#         log_command("list measurements trunk-group summary yesterday-peak", "Failed", None, str(e), 0)

#         return jsonify({"error": str(e)}), 500

@app.route("/get-yesterday-peak-data", methods=["POST"])
def get_yesterday_peak_data():
    """
    Run 'list measurements trunk-group summary yesterday-peak',
    parse output in memory, and return JSON + Excel path.
    """
    try:
        start_time = time.time()

        # --- NEW: Read JSON input ---
        req = request.get_json(force=True)
        ip = req.get("ip")
        password = req.get("password")

        if not ip or not password:
            return jsonify({"error": "Missing IP or password"}), 400

        # --- NEW: run with dynamic credentials ---
        output = run_yesterday_peak(ip, password)

        if not output or output.strip() == "":
            return jsonify({"error": "Empty output from SAT command"}), 500

        # Parse the trunk table
        df = parse_trunk_summary(output)

        # Save to Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = "list_measurements_trunk-group_summary_yesterday-peak"
        excel_file = os.path.join(REPORT_DIR, f"{safe_prefix}_{timestamp}.xlsx")
        df.to_excel(excel_file, index=False)

        # Convert to JSON for UI
        data_json = json.loads(df.to_json(orient="records"))
        columns = df.columns.tolist()
        duration = round(time.time() - start_time, 2)

        # Log command
        log_command("list measurements trunk-group summary yesterday-peak",
                    "success", excel_file, f"{len(df)} rows", duration)

        return jsonify({
            "data": data_json,
            "columns": columns,
            "excel_path": excel_file
        })

    except Exception as e:
        print(f"❌ Error in /get-yesterday-peak-data: {e}")
        return jsonify({"error": str(e)}), 500





@app.route("/download-yesterday-peak", methods=["GET"])
def download_yesterday_peak():
    """Send the latest Excel file to the browser for download."""
    try:
        latest = get_latest_excel()
        if not latest:
            return jsonify({"error": "No Excel file found to download"}), 404

        # send as attachment so browser downloads it
        return send_file(
            latest,
            as_attachment=True,
            download_name=os.path.basename(latest),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        print("[Backend] ❌ Download error:", e)
        return jsonify({"error": str(e)}), 500    








def get_latest_monitor_excel():
    files = glob.glob(os.path.join(EXCEL_DIR, MONITOR_PATTERN))
    if not files:
        print("[Backend] No monitor traffic trunk-groups Excel found.")
        return None
    latest = max(files, key=os.path.getmtime)
    print(f"[Backend] Latest monitor Excel: {latest}")
    return latest

@app.route("/run-monitor-traffic-trunk-groups", methods=["POST"])
def run_monitor_traffic_trunk_groups_old():
    try:
        before = get_latest_monitor_excel()
        before_time = os.path.getmtime(before) if before else 0

        print(f"[Backend] Running: {MONITOR_SCRIPT}")
        subprocess.run(["python3", MONITOR_SCRIPT], check=True)

        timeout = 40
        start = time.time()
        new_file = None
        while time.time() - start < timeout:
            latest = get_latest_monitor_excel()
            if latest and (not before or os.path.getmtime(latest) > before_time):
                new_file = latest
                break
            time.sleep(1)

        if not new_file:
            msg = "[Backend] ❌ No new monitor excel created!"
            print(msg)
            return jsonify({"error": msg}), 500

        # after you found new_file and before returning success
        duration = round(time.time() - start, 2)  # if you have start_time stored
        log_command("monitor-traffic-trunk-groups", "Success", new_file, "Excel created", duration)






        print(f"[Backend] ✅ New monitor Excel ready: {new_file}")
        return jsonify({
            "success": True,
            "excel_path": f"/reports/{os.path.basename(new_file)}"
        })

    except subprocess.CalledProcessError as e:
        print("[Backend] Script failed:", e)
        return jsonify({"error": f"Script failed: {str(e)}"}), 500
    except Exception as e:
        log_command("monitor-traffic-trunk-groups", "Failed", None, str(e), 0)



        print("[Backend] Exception:", e)
        return jsonify({"error": str(e)}), 500

# @app.route("/get-monitor-traffic-trunk-groups-data", methods=["GET"])
# def get_monitor_traffic_trunk_groups_data():
#     try:
#         latest = get_latest_monitor_excel()
#         if not latest:
#             return jsonify({"error": "No monitor Excel found"}), 404
#         df = pd.read_excel(latest)
#         data = df.to_dict(orient="records")
#         return jsonify({
#             "data": data,
#             "excel_path": f"/reports/{os.path.basename(latest)}"
#         })
#     except Exception as e:
#         print("[Backend] Read error:", e)
#         return jsonify({"error": str(e)}), 500


@app.route("/get-monitor-traffic-trunk-groups-data", methods=["POST"])
def get_monitor_traffic_trunk_groups_data():
    """
    Run 'monitor traffic trunk-groups',
    parse output in memory, and return JSON + Excel path.
    """
    try:
        start_time = time.time()

        # EXACT SAME GET/POST HANDLING AS YESTERDAY PEAK
        if request.method == "POST":
            req = request.get_json(force=True)
        else:
            req = request.args

        ip = req.get("ip")
        password = req.get("password")

        # If GET: just return empty (same behavior as your other endpoints)


        # POST mode → execute SAT command
        output = run_monitor_traffic_trunk_groups(ip, password)

        if not output or output.strip() == "":
            return jsonify({"error": "Empty output from SAT command"}), 500

        df = parse_monitor_traffic_output(output)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = "monitor_traffic_trunk-groups"
        excel_file = os.path.join(REPORT_DIR, f"{safe_prefix}_{timestamp}.xlsx")
        df.to_excel(excel_file, index=False)

        data_json = json.loads(df.to_json(orient="records"))
        columns = df.columns.tolist()
        duration = round(time.time() - start_time, 2)

        log_command(
            "monitor traffic trunk-groups",
            "success",
            excel_file,
            f"{len(df)} rows",
            duration
        )

        return jsonify({
            "data": data_json,
            "columns": columns,
            "excel_path": excel_file
        })

    except Exception as e:
        print(f"❌ Error in /get_monitor_traffic_trunk_groups_data: {e}")
        return jsonify({"error": str(e)}), 500






@app.route("/download-monitor-traffic-trunk-groups", methods=["GET"])
def download_monitor_traffic_trunk_groups():
    try:
        latest = get_latest_monitor_excel()
        if not latest:
            return jsonify({"error": "No Excel file found"}), 404
        return send_file(
            latest,
            as_attachment=True,
            download_name=os.path.basename(latest),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        print("[Backend] Download error:", e)
        return jsonify({"error": str(e)}), 500









def get_latest_file_for_status_trunk(trunk):
    """
    Find the latest file for status_trunk_<trunk>_*.xlsx inside REPORT_DIR
    """
    pattern = os.path.join(REPORT_DIR, f"status_trunk_{trunk}_*.xlsx")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

# @app.route("/run-status-trunk", methods=["POST"])
# def run_status_trunk():
#     """
#     Runs backend/status_trunk.py automatically for all trunk groups.
#     No user input required.
#     """
#     try:
#         print("[Backend] Running status_trunk.py for all trunk groups...")
#         script_path = os.path.join(os.path.dirname(__file__), "status_trunk.py")

#         # Run the automated script
#         start_time = time.time()
#         subprocess.run(["python3", script_path], check=True)

#         # Wait for the new combined Excel file
#         pattern = os.path.join(REPORT_DIR, "status_trunk_all_*.xlsx")
#         files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
#         new_file = files[-1] if files else None

#         if not new_file or not os.path.exists(new_file):
#             msg = "[Backend] ❌ No Excel file created by status_trunk.py"
#             print(msg)
#             return jsonify({"error": msg}), 500

#         duration = round(time.time() - start_time, 2)
#         log_command("status trunk all", "Success", new_file, "Excel created", duration)

#         print(f"[Backend] ✅ status_trunk.py completed: {new_file}")
#         return jsonify({
#             "success": True,
#             "excel_path": new_file
#         })

#     except subprocess.CalledProcessError as e:
#         err = f"status_trunk.py failed: {str(e)}"
#         print("[Backend] ❌", err)
#         log_command("status trunk all", "Failed", None, err, 0)
#         return jsonify({"error": err}), 500
#     except Exception as e:
#         print("[Backend] ❌ Exception:", e)
#         log_command("status trunk all", "Failed", None, str(e), 0)
#         return jsonify({"error": str(e)}), 500



# === Replace the old /run-status-trunk endpoint with this dynamic implementation ===
@app.route("/run-status-trunk", methods=["POST"])
def run_status_trunk():
    """
    Runs backend/status_trunk.py automatically for all trunk groups.
    No user input required.
    """
    try:
        # Try to read POST JSON if present, but don't force (prevents 400)
        req = request.get_json(silent=True) or {}
        ip = req.get("ip")
        password = req.get("password")

        # If no creds in body, fallback to saved creds helper (works like other endpoints)
        if not ip or not password:
            ip, password = _get_creds_from_request_or_saved()
            if not ip or not password:
                return jsonify({"error": "Missing ip/password"}), 400


        start_time = time.time()
        print("[Backend] Running status_trunk.py for all trunk groups...")
        script_path = os.path.join(os.path.dirname(__file__), "status_trunk.py")

        # run_status_trunk_all returns absolute excel path (or None on failure)
        excel_path = run_status_trunk_all(ip, password)

        if not excel_path:
            msg = "[Backend] ❌ status_trunk wrapper returned no excel (no data / failed)."
            print(msg)
            log_command("status trunk all", "Failed", None, "No output", 0)
            return jsonify({"error": msg}), 500

        duration = round(time.time() - start_time, 2)
        log_command("status trunk all", "Success", excel_path, "Excel created", duration)

        print(f"[Backend] ✅ status_trunk completed: {excel_path}")
        return jsonify({"success": True, "excel_path": excel_path})

    except Exception as e:
        print("[Backend] ❌ Exception in /run-status-trunk:", e)
        log_command("status trunk all", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500




# @app.route("/get-status-trunk-data", methods=["GET"])
# def get_status_trunk_data():
#     """
#     GET ?trunk=<num>
#     Reads latest Excel for the trunk and returns JSON:
#     { "data": [ {col:val,...}, ... ], "excel_path": "<path>" }
#     """
#     try:
#         trunk = request.args.get("trunk", "").strip()
#         if not trunk:
#             return jsonify({"error": "trunk number required"}), 400

#         latest = get_latest_file_for_status_trunk(trunk)
#         if not latest:
#             return jsonify({"data": [], "excel_path": None})

#         # read into dataframe
#         df = pd.read_excel(latest, sheet_name=0)
#         data = df.fillna("").to_dict(orient="records")
#         return jsonify({"data": data, "excel_path": latest})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500


# === Replace /get-status-trunk-data with this upgraded version (GET + POST support) ===
@app.route("/get-status-trunk-data", methods=["GET", "POST"])
def get_status_trunk_data():
    """
    GET ?trunk=<num>
      - Reads latest Excel for that trunk and returns JSON (backward compatible).

    POST JSON: { "ip": "...", "password": "...", "trunk": "<num>" }
      - Runs SAT 'status trunk <trunk>' dynamically using provided credentials,
        parses the output and returns JSON rows (no intermediate Excel required).
    """
    try:
        # POST -> run live for a single trunk (preferred when ip/password passed)
        if request.method == "POST":
            req = request.get_json(force=True)
            ip = req.get("ip")
            password = req.get("password")
            trunk = str(req.get("trunk") or "").strip()

            if not trunk:
                return jsonify({"error": "trunk number required in POST body"}), 400

            # fallback to saved creds if ip/password not provided
            if not ip or not password:
                ip, password = _get_creds_from_request_or_saved()
                if not ip or not password:
                    return jsonify({"error": "Missing IP/password for POST run"}), 400

            # Run single trunk command dynamically and parse
            raw = run_status_trunk(ip, password, trunk)
            if not raw or not raw.strip():
                return jsonify({"error": "Empty output from SAT command"}), 500

            df = parse_status_trunk(raw)
            # ensure DataFrame -> JSON safe
            data = df.fillna("").to_dict(orient="records")
            # Optionally save a small per-trunk excel (keep parity with other endpoints)
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fn = os.path.join(REPORT_DIR, f"status_trunk_{trunk}_{ts}.xlsx")
                df.to_excel(fn, index=False)
                excel_path = fn
            except Exception:
                excel_path = None

            duration = 0  # we can skip precise timing here or compute if desired
            log_command(f"status trunk {trunk}", "success" if len(data) else "no-data", excel_path, f"{len(data)} rows", duration)

            return jsonify({"data": data, "columns": df.columns.tolist(), "excel_path": excel_path})

        # GET -> fallback to reading latest excel (existing behaviour)
        trunk = request.args.get("trunk", "").strip()
        if not trunk:
            return jsonify({"error": "trunk number required"}), 400

        latest = get_latest_file_for_status_trunk(trunk)
        if not latest:
            return jsonify({"data": [], "excel_path": None})

        df = pd.read_excel(latest, sheet_name=0)
        data = df.fillna("").to_dict(orient="records")
        return jsonify({"data": data, "excel_path": latest})

    except Exception as e:
        print("[Backend] ❌ Error in /get-status-trunk-data:", e)
        log_command(f"status trunk {request.args.get('trunk','?')}", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500




# @app.route("/get-status-trunk-all-data", methods=["GET"])
# def get_status_trunk_all_data():
#     """
#     Reads the latest combined Excel for all trunk groups and returns JSON.
#     """
#     try:
#         pattern = os.path.join(REPORT_DIR, "status_trunk_all_*.xlsx")
#         files = glob.glob(pattern)
#         if not files:
#             return jsonify({"error": "No combined trunk Excel found"}), 404

#         latest = max(files, key=os.path.getmtime)
#         df = pd.read_excel(latest, sheet_name=0)
#         data = df.fillna("").to_dict(orient="records")

#         return jsonify({
#             "data": data,
#             "columns": df.columns.tolist(),
#             "excel_path": latest
#         })
#     except Exception as e:
#         print(f"❌ Error reading combined trunk Excel: {e}")
#         return jsonify({"error": str(e)}), 500


# === (Optionally) keep your get-status-trunk-all-data route but ensure it can accept saved creds ===
@app.route("/get-status-trunk-all-data", methods=["GET"])
def get_status_trunk_all_data():
    try:
        pattern = os.path.join(REPORT_DIR, "status_trunk_all_*.xlsx")
        files = glob.glob(pattern)
        if not files:
            return jsonify({"error": "No combined trunk Excel found"}), 404

        latest = max(files, key=os.path.getmtime)
        df = pd.read_excel(latest, sheet_name=0)
        data = df.fillna("").to_dict(orient="records")

        return jsonify({
            "data": data,
            "columns": df.columns.tolist(),
            "excel_path": latest
        })
    except Exception as e:
        print(f"❌ Error reading combined trunk Excel: {e}")
        return jsonify({"error": str(e)}), 500




# get-list-measurements-outage-trunk-last-hour

@app.route("/get-list-measurements-outage-trunk-last-hour", methods=["GET", "POST"])
def get_list_measurements_outage_trunk_last_hour():
    import re
    import pandas as pd
    from flask import jsonify
    import os, time

    try:
        start = time.time()

        # ✅ REQUIRED (fix for NoneType output)
        ip, password = _get_creds_from_request_or_saved()
        if not ip or not password:
            return jsonify({"error": "Missing IP or password"}), 400

        # Inject credentials into SAT module (CORRECT WAY)
        import yesterday_peak
        yesterday_peak.SAT_HOST = ip
        yesterday_peak.SAT_PASSWORD = password
        yesterday_peak.SAT_USERNAME = "dadmin"


        # Run Avaya command
        output = run_avaya_command("list measurements outage-trunk last-hour")

        # print("=== DEBUG: RAW OUTAGE OUTPUT ===")
        # print(repr(output))
        # print("================================")


        if not output:
            return jsonify({"error": "Empty output received"}), 500

        # Parse rows
        data_lines = re.findall(r"(?m)^\s*\d+\s+.*", output)

        filtered_lines = []
        for line in data_lines:
            if re.search(r"press\s+(CANCEL|NEXT PAGE|to quit)", line, re.IGNORECASE):
                continue
            filtered_lines.append(line)

        if not filtered_lines:
            return jsonify({"error": "No valid trunk data found"}), 500

        parsed_rows = []
        for line in filtered_lines:
            line = re.sub(r"\s+", " ", line.strip())
            tokens = []
            for part in line.split(" "):
                split_parts = re.findall(r"[A-Za-z#]+|\d+", part)
                tokens.extend(split_parts)
            tokens = (tokens + [""] * 6)[:6]
            parsed_rows.append(tokens)

        columns = ["Grp No.", "Grp Type", "Grp Dir", "Grp Siz", "Grp Mbr#", "#Sampled Outages"]

        df = pd.DataFrame(parsed_rows, columns=columns)
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"list_measurements_outage_trunk_last_hour_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        duration = round(time.time() - start, 2)
        log_command("list measurements outage-trunk last-hour", "Success", excel_path, f"{len(df)} rows", duration)

        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in outage-trunk last-hour: {e}")
        log_command("list measurements outage-trunk last-hour", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500







@app.route("/get-status-aesvcs-cti-link", methods=["GET", "POST"])
def get_status_aesvcs_cti_link():
    """
    Runs 'status aesvcs cti-link' on Avaya, parses properly spaced output,
    saves Excel, and returns JSON.
    """
    import re
    import pandas as pd
    import os, time

    try:
        start = time.time()
        print("⚙️ Running Avaya command: status aesvcs cti-link")

        output = run_avaya_command("status aesvcs cti-link")

        if not output or len(output.strip()) == 0:
            return jsonify({"error": "No output from Avaya command"}), 500

        # ✅ Filter out non-data lines
        cleaned_lines = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.search(r"Page\s+\d+", line, re.IGNORECASE):
                continue
            if "AE SERVICES CTI LINK STATUS" in line.upper():
                continue
            if "press" in line.lower() or "Command" in line or "CANCEL" in line:
                continue
            if any(
                hdr in line
                for hdr in ["CTI", "Version", "Busy", "Server", "State", "Msgs"]
            ):
                continue

            if re.match(r"^\d+", line):  # data lines start with a number
                clean = re.sub(r"\s+", " ", line.strip())
                cleaned_lines.append(clean)

        if not cleaned_lines:
            print("⚠️ No valid CTI link data found.")
            return jsonify({"error": "No valid CTI link data found"}), 500

        # ✅ Parse each data row correctly (7 columns)
        data_rows = []
        for line in cleaned_lines:
            # ✅ Fix known merge patterns (10no → 10 no, aes7038 → aes7038)
            line = re.sub(r"(\d{2})(no)", r"\1 \2", line)  # fixes 10no
            line = re.sub(r"(\baes)(\d+)\b", r"\1\2", line)  # keeps aes7038 together
            line = re.sub(r"\s+", " ", line.strip())

            # Split into tokens
            parts = re.split(r"\s+", line)

            # Re-join aes7038 if still split accidentally
            if len(parts) >= 5 and parts[3] == "aes" and re.match(r"^\d+$", parts[4]):
                parts[3] = parts[3] + parts[4]
                del parts[4]


            # Expected 7 columns: CTI Link, Version, Mnt Busy, AE Server, State, Msgs Sent, Msgs Rcvd
            if len(parts) < 7:
                parts += [""] * (7 - len(parts))
            elif len(parts) > 7:
                parts = parts[:7]

            data_rows.append(parts)


        columns = [
            "CTI Link",
            "Version",
            "Mnt Busy",
            "AE Services Server",
            "Service State",
            "Msgs Sent",
            "Msgs Rcvd",
        ]

        # ✅ Build DataFrame
        df = pd.DataFrame(data_rows, columns=columns)
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_aesvcs_cti_link{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        #

        # ✅ Log success
        duration = round(time.time() - start, 2)
        log_command("status aesvcs cti-link", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} CTI rows → Excel: {excel_path}")
        for row in df.to_dict(orient="records"):
            print(row)


        print("=== DEBUG FINAL PARSED CTI LINK ROWS ===")
        for row in df.to_dict(orient="records"):
            print(row)
        print("========================================")


        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in status aesvcs cti-link: {e}")
        log_command("status aesvcs cti-link", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500









  
@app.route("/get-list-survivable-processor-data", methods=["GET", "POST"])
def get_list_survivable_processor_data():
    """
    Runs 'list survivable-processor' on Avaya, parses output,
    saves Excel, and returns JSON.
    """
    import re
    import pandas as pd
    import os, time

    try:
        start = time.time()
        print("⚙️ Running Avaya command: list survivable-processor")

        output = run_avaya_command("list survivable-processor")





        if not output or len(output.strip()) == 0:
            print("❌ No output from Avaya command!")
            return jsonify({"error": "No output from Avaya command"}), 500

        cleaned_lines = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if "SURVIVABLE" in line or "Record" in line or "Number" in line:
                continue
            if "Command successfully" in line or "press" in line.lower():
                continue
            if re.search(r"Page\s+\d+", line, re.IGNORECASE):
                continue
            if "CANCEL" in line:
                continue
            cleaned_lines.append(line)

        if not cleaned_lines:
            return jsonify({"error": "No valid survivable-processor data found"}), 500

        # --- Parse logic ---
        data_rows = []
        current = {}

        for line in cleaned_lines:
            parts = line.split()

            # Detect start of a new record: line starts with a number (allow spaces)
            if re.match(r"^\d+", line.strip()):
                if current:
                    data_rows.append(current)

                record_number = parts[0]
                # Remainder of the first line is just the name
                name = " ".join(parts[1:])
                current = {
                    "Record number": record_number,
                    "Name/IP address": name,
                    "Type": "",
                    "Reg": "",
                    "Ack": "",
                    "Translations updated": "",
                    "Net Rgn": ""
                }

            # If the line starts with an IP (contains dots) and we have an active record
            elif current and re.search(r"\d+\.\d+\.\d+\.\d+", line):
                tokens = re.split(r"\s+", line)
                # Example: 10.52.32.10 LSP y y 16:35 10/14/2025 24
                if len(tokens) >= 7:
                    current["Name/IP address"] += f" {tokens[0]}"
                    current["Type"] = tokens[1]
                    current["Reg"] = tokens[2]
                    current["Ack"] = tokens[3]
                    current["Translations updated"] = f"{tokens[4]} {tokens[5]}"
                    current["Net Rgn"] = tokens[6]
                else:
                    current["Name/IP address"] += " " + " ".join(tokens)

        if current:
            data_rows.append(current)

        # --- Build DataFrame ---
        columns = [
            "Record number",
            "Name/IP address",
            "Type",
            "Reg",
            "Ack",
            "Translations updated",
            "Net Rgn"
        ]
        df = pd.DataFrame(data_rows, columns=columns)

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"list_survivable_processor_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        # list_survivable_processor

        duration = round(time.time() - start, 2)
        log_command("list survivable-processor", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} survivable processor rows → Excel: {excel_path}")
        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in list survivable-processor: {e}")
        log_command("list survivable-processor", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500






@app.route("/get-status-media-gateway", methods=["GET", "POST"])
def get_status_media_gateway():
    import re
    import pandas as pd
    from flask import jsonify
    import os, time

    try:
        start = time.time()
        output = run_avaya_command("status media-gateway")

        print("\n=== DEBUG MEDIA-GATEWAY OUTPUT ===")
        print(repr(output[:2000]))
        print("=== END DEBUG ===\n")

        # --- Handle no-data cases ---
        if re.search(r"No data in the system to list", output, re.IGNORECASE) or \
           re.search(r"No records match", output, re.IGNORECASE):
            df = pd.DataFrame([{"Message": "No data in the system to list"}])
            os.makedirs("outputs", exist_ok=True)
            excel_path = os.path.join("outputs", "status_media_gateway.xlsx")
            df.to_excel(excel_path, index=False)
            log_command("status media-gateway", "Success", excel_path, "No data", 0)
            return jsonify({
                "summary": {},
                "data": [],
                "columns": [],
                "excel_path": excel_path,
                "note": "No data in the system to list"
            })

        # --- Extract summary values ---
        section = re.sub(r"\s+", " ", output.strip())
        summary = {
            "Major": re.search(r"Major:\s*(\d+)", section).group(1) if re.search(r"Major:\s*(\d+)", section) else "0",
            "Minor": re.search(r"Minor:\s*(\d+)", section).group(1) if re.search(r"Minor:\s*(\d+)", section) else "0",
            "Warning": re.search(r"Warning:\s*(\d+)", section).group(1) if re.search(r"Warning:\s*(\d+)", section) else "0",
            "Trunks": re.search(r"Trunks:\s*(\d+)", section).group(1) if re.search(r"Trunks:\s*(\d+)", section) else "0",
            "Stations": re.search(r"Stations:\s*(\d+)", section).group(1) if re.search(r"Stations:\s*(\d+)", section) else "0",
            "Links Down": re.search(r"Links Down:\s*(\d+)", section).group(1) if re.search(r"Links Down:\s*(\d+)", section) else "0",
            "Links Up": re.search(r"Links Up:\s*(\d+)", section).group(1) if re.search(r"Links Up:\s*(\d+)", section) else "0",
            "# Logins": re.search(r"# Logins:\s*(\d+)", section).group(1) if re.search(r"# Logins:\s*(\d+)", section) else "0"
        }

        # --- Extract Gateway Status block ---
        gw_block = re.search(r"GATEWAY STATUS(.*?)Command:", output, re.DOTALL | re.IGNORECASE)
        gateways_data = []

        if gw_block:
            text = gw_block.group(1)
            # Remove the header lines
            text = re.sub(r"Alarms", "", text)
            text = re.sub(r"(MG\s+Mj\s+Mn\s+Wn\s+Lk)+", "", text, flags=re.IGNORECASE)
            text = text.strip()

            # Split into tokens
            tokens = re.findall(r"[A-Za-z0-9]+", text)
            print("🧩 Extracted tokens from GATEWAY STATUS:", tokens)

            # Filter out command echoes like "7", "8", "Command", etc.
            ignore_tokens = {"7", "8", "Command"}
            tokens = [t for t in tokens if t not in ignore_tokens]

            # Build MG rows only if the token looks like an MG identifier (starts with digit or letter)
            # Group in chunks of 5 if full MG rows appear; otherwise skip
            for i in range(0, len(tokens), 5):
                chunk = tokens[i:i+5]
                if len(chunk) == 5 and chunk[0].upper() != "MG":
                    gateways_data.append({
                        "MG": chunk[0],
                        "Mj": chunk[1],
                        "Mn": chunk[2],
                        "Wn": chunk[3],
                        "Lk": chunk[4]
                    })

        df_gateways = pd.DataFrame(gateways_data, columns=["MG", "Mj", "Mn", "Wn", "Lk"])

        # --- Save Excel ---
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_media_gateway_{timestamp}.xlsx")

        df_gateways.to_excel(excel_path, index=False)

        # status_media_gateway

        log_command("status media-gateway", "Success", excel_path, f"{len(df_gateways)} gateways", 0)
        print(f"✅ Parsed {len(df_gateways)} gateway rows → Excel: {excel_path}")

        # --- Return for UI ---
        return jsonify({
            "summary": summary,
            "data": df_gateways.to_dict(orient="records"),
            "columns": df_gateways.columns.tolist(),
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in status media-gateway: {e}")
        log_command("status media-gateway", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500













@app.route("/get-status-media-processor-all", methods=["GET", "POST"])
def get_status_media_processor_all():
    import re
    import pandas as pd
    from flask import jsonify
    import os, time
    from io import StringIO

    try:
        start = time.time()

        # ✅ Run the Avaya command
        output = run_avaya_command("status media-processor all")

        # --- Optional Debug ---
        print("\n=== DEBUG MEDIA-PROCESSOR OUTPUT ===")
        for i, line in enumerate(output.splitlines()[:40], 1):
            print(f"{i:02d}: {line}")
        print("=== END DEBUG ===\n")

        # ✅ Handle cases where Avaya returns no usable data
        if re.search(r"No data in the system to list", output, re.IGNORECASE) or \
        re.search(r"No records match the specified query", output, re.IGNORECASE):
            print("ℹ️ No data found for status media-processor all.")
            os.makedirs("outputs", exist_ok=True)
            excel_path = os.path.join("outputs", "status_media_processor_all.xlsx")

            df = pd.DataFrame([{"Message": "No records match the specified query options"}])
            df.to_excel(excel_path, index=False)

            duration = round(time.time() - start, 2)
            log_command("status media-processor all", "Success", excel_path, "No data available", duration)

            return jsonify({
                "data": [],
                "columns": ["Message"],
                "excel_path": excel_path,
                "note": "No records match the specified query options"
            })


        # ✅ Define known column headers for this command
        columns = [
            "Board",
            "IP Address",
            "Network Region",
            "Link Status",
            "Mode",
            "VoIP Channels (Used/Avail)",
            "Service State"
        ]

        # ✅ Capture all valid data lines (usually start with board numbers or IPs)
        data_lines = re.findall(r"(?m)^\s*\S+\s+.*", output)

        # Filter out Avaya paging prompts
        filtered_lines = [
            line for line in data_lines
            if not re.search(r"press\s+(CANCEL|NEXT PAGE|to quit)", line, re.IGNORECASE)
        ]

        if not filtered_lines:
            print("❌ No valid media-processor data lines found.")
            return jsonify({"error": "No valid processor data found"}), 500

        # ✅ Regex-based flexible parser
        parsed_rows = []
        for line in filtered_lines:
            line = re.sub(r"\s+", " ", line.strip())
            # This pattern splits merged alphanumeric groups and keeps IPs intact
            parts = re.findall(r"\d+\.\d+\.\d+\.\d+|[A-Za-z#/:\-\(\)]+|\d+", line)
            parsed_rows.append(parts)

        # ✅ Pad or truncate to expected columns
        for row in parsed_rows:
            row.extend([""] * (len(columns) - len(row)))
            if len(row) > len(columns):
                row[:] = row[:len(columns)]

        # ✅ Build DataFrame
        df = pd.DataFrame(parsed_rows, columns=columns)
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        # ✅ Save Excel for UI download
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_media_processor_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        # status_media_processor

        # ✅ Log command success
        duration = round(time.time() - start, 2)
        log_command("status media-processor all", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} rows → Excel: {excel_path}")
        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in status media-processor all: {e}")
        log_command("status media-processor all", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500





@app.route("/get-status-aesvcs-interface", methods=["GET", "POST"])
def get_status_aesvcs_interface():
    """
    Runs 'status aesvcs interface' on Avaya,
    parses output, saves Excel, and returns JSON.
    """
    import re
    import pandas as pd
    import os, time

    try:
        start = time.time()
        print("⚙️ Running Avaya command: status aesvcs interface")

        # ✅ Run Avaya command
        output = run_avaya_command("status aesvcs interface")

        if not output or len(output.strip()) == 0:
            print("❌ No output from Avaya command!")
            return jsonify({"error": "No output from Avaya command"}), 500

        print("\n=== RAW AESVCS INTERFACE OUTPUT (first 20 lines) ===")
        for i, line in enumerate(output.splitlines()[:20], 1):
            print(f"{i:02d}: {line}")
        print("====================================================\n")

        # ✅ Clean and collect only useful lines
        cleaned_lines = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if "AE SERVICES INTERFACE STATUS" in line.upper():
                continue
            if "Command successfully" in line or "Command:" in line:
                continue
            if "Local Node" in line or "Enabled?" in line:
                continue
            if "Connections" in line and not line.startswith("procr"):
                # skip header fragment
                continue
            if re.match(r"^\S+", line):  # keep data lines
                # normalize spacing
                cleaned_lines.append(re.sub(r"\s+", " ", line))

        if not cleaned_lines:
            print("⚠️ No valid AESVCS interface data found.")
            return jsonify({"error": "No valid AESVCS interface data found"}), 500

        # ✅ Parse each data row
        data_rows = []
        for line in cleaned_lines:
            # Example: procr yes1 listening  →  procr yes 1 listening
            line = re.sub(r"(\D)(\d+)", r"\1 \2", line)  # split letter-number
            line = re.sub(r"(\d)([A-Za-z])", r"\1 \2", line)  # split number-letter
            parts = re.split(r"\s+", line.strip())

            # Expected 4 columns: Local Node, Enabled?, Number of Connections, Status
            if len(parts) < 4:
                parts += [""] * (4 - len(parts))
            parts = parts[:4]
            data_rows.append(parts)

        columns = ["Local Node", "Enabled?", "Number of Connections", "Status"]

        # ✅ Create DataFrame
        df = pd.DataFrame(data_rows, columns=columns)
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        # ✅ Save Excel
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_aesvcs_interface_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        # status_aesvcs_interface

        # ✅ Log success
        duration = round(time.time() - start, 2)
        log_command("status aesvcs interface", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} AESVCS interface rows → Excel: {excel_path}")

        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in status aesvcs interface: {e}")
        log_command("status aesvcs interface", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500






@app.route("/get-status-aesvcs-link", methods=["GET", "POST"])
def get_status_aesvcs_link():
    """
    Runs 'status aesvcs link' on Avaya, handles multi-line screen output,
    saves Excel, and returns JSON.
    """
    import re
    import pandas as pd
    import os, time

    try:
        start = time.time()
        print("⚙️ Running Avaya command: status aesvcs link")

        output = run_avaya_command("status aesvcs link")

        if not output or len(output.strip()) == 0:
            return jsonify({"error": "No output from Avaya command"}), 500

        # --- Clean lines ---
        lines = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(skip in line for skip in [
                "AE SERVICES LINK STATUS",
                "Command successfully",
                "press",
                "Command:",
                "Page",
                "Srvr", "Link", "AE Services", "Remote"
            ]):
                continue
            lines.append(line)

        if not lines:
            return jsonify({"error": "No valid AES link data found"}), 500

        # --- Combine continuation lines (IP appears after numeric row) ---
        merged = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # If next line is an IP → append to current
            if i + 1 < len(lines) and re.search(r"\d+\.\d+\.\d+\.\d+", lines[i + 1]):
                line += " " + lines[i + 1].strip()
                i += 1
            merged.append(line)
            i += 1

        data_rows = []
        for line in merged:
            # Example:
            # "01/01aes7038 53576procr 629 614 172.16.70.38"
            line = re.sub(r"(\d+/\d+)([A-Za-z])", r"\1 \2", line)  # split 01/01aes
            line = re.sub(r"(\d{3,5})(procr)", r"\1 \2", line)     # split 53576procr

            tokens = re.split(r"\s+", line.strip())

            # Expect something like:
            # ['01/01', 'aes7038', '53576', 'procr', '629', '614', '172.16.70.38']
            if len(tokens) < 7:
                continue

            srvr_link = tokens[0]
            ae_server = tokens[1]
            remote_port = tokens[2]
            local_node = tokens[3]
            msgs_sent = tokens[4]
            msgs_rcvd = tokens[5]
            remote_ip = tokens[6] if re.match(r"\d+\.\d+\.\d+\.\d+", tokens[6]) else ""

            data_rows.append([
                srvr_link, ae_server, remote_ip, remote_port,
                local_node, msgs_sent, msgs_rcvd
            ])

        columns = [
            "Srvr/Link",
            "AE Services Server",
            "Remote IP",
            "Remote Port",
            "Local Node",
            "Msgs Sent",
            "Msgs Rcvd",
        ]

        df = pd.DataFrame(data_rows, columns=columns)
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_aesvcs_link_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        # status_aesvcs_link

        duration = round(time.time() - start, 2)
        log_command("status aesvcs link", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} AES link rows → Excel: {excel_path}")

        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in status aesvcs link: {e}")
        log_command("status aesvcs link", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500






@app.route("/get-status-cdr-link", methods=["GET", "POST"])
def get_status_cdr_link():
    import re
    import pandas as pd
    from flask import jsonify
    import os, time

    try:
        start = time.time()
        output = run_avaya_command("status cdr-link")

        # Debug (keeps original raw string visible in logs)
        print("\n=== RAW DEBUG (repr) ===")
        print(repr(output[:2000]))
        print("=== END RAW DEBUG ===\n")

        # Handle common "no data" messages
        if re.search(r"No data in the system to list", output, re.IGNORECASE) or \
           re.search(r"No records match", output, re.IGNORECASE):
            os.makedirs("outputs", exist_ok=True)
            excel_path = os.path.join("outputs", "status_cdr_link.xlsx")
            df = pd.DataFrame([{"Message": "No data in the system to list"}])
            df.to_excel(excel_path, index=False)
            log_command("status cdr-link", "Success", excel_path, "No data", 0)
            return jsonify({"data": [], "columns": ["Message"], "excel_path": excel_path, "note": "No data in the system to list"})

        # Isolate the CDR LINK STATUS section
        m = re.search(r"CDR LINK STATUS(.*?)(?:Command:|$)", output, re.DOTALL | re.IGNORECASE)
        section = m.group(1) if m else output

        # Normalize spacing and lines
        section = section.replace("\t", " ")
        section = re.sub(r"\r\n", "\n", section)
        # collapse repeated blank lines to single blank line to simplify indexing
        section = re.sub(r"\n{2,}", "\n\n", section).strip()

        # Remove clear footer/noise tokens
        section = re.sub(r"(?i)press\s+CANCEL.*", "", section)
        section = re.sub(r"(?i)command\s+successfully.*", "", section)
        section = re.sub(r"\b\d+\s*\Z", "", section).strip()

        # Prepare lines for lookups
        lines = [ln.rstrip() for ln in section.splitlines()]

        # Expected parameter names in order
        expected = [
            "Link State",
            "Date & Time",
            "Forward Seq. No",
            "Backward Seq. No",
            "CDR Buffer % Full",
            "Reason Code"
        ]

        # Helper: given a label, find the line index containing 'Label:' (case-insensitive).
        def find_label_line_idx(label):
            pattern = re.compile(re.escape(label) + r"\s*:", re.IGNORECASE)
            for idx, ln in enumerate(lines):
                if pattern.search(ln):
                    return idx
            return None

        rows = []
        for label in expected:
            idx = find_label_line_idx(label)
            primary = ""
            secondary = ""
            if idx is not None:
                # get the content after the colon on the same line (if any)
                line = lines[idx]
                after = re.sub(r"(?i)^.*?\:\s*", "", line).strip()
                if after:
                    # If two columns separated by 2+ spaces -> split
                    parts = re.split(r"\s{2,}", after)
                    if len(parts) >= 2:
                        primary = parts[0].strip()
                        secondary = parts[1].strip()
                    else:
                        # single token on the same line — treat as primary
                        primary = after.strip()
                        # Try to see if there's a secondary on the same physical line further right
                        # (some outputs have aligned columns with many spaces; attempt a broader split)
                        if re.search(r"\s{3,}", line):
                            parts2 = re.split(r"\s{3,}", line)
                            # parts2 may include the label itself; remove first fragment that contains label
                            if len(parts2) >= 2:
                                # pick last two fragments as primary/secondary if they look like values
                                cand = [p.strip() for p in parts2 if p.strip() and not re.search(r"(?i)^" + re.escape(label) + r"\s*:", p)]
                                if len(cand) >= 2:
                                    primary, secondary = cand[-2], cand[-1]
                else:
                    # No content after colon — check the next non-empty line for values
                    j = idx + 1
                    while j < len(lines) and lines[j].strip() == "":
                        j += 1
                    if j < len(lines):
                        nextline = lines[j].strip()
                        parts = re.split(r"\s{2,}", nextline)
                        if len(parts) >= 2:
                            primary = parts[0].strip()
                            secondary = parts[1].strip()
                        else:
                            # fallback: maybe values are on the next line separated by multiple spaces
                            primary = nextline.strip()
                            # Attempt to extract second column from same nextline using big gap heuristic
                            if re.search(r"\s{3,}", lines[j]):
                                cand = [p.strip() for p in re.split(r"\s{3,}", lines[j]) if p.strip()]
                                if len(cand) >= 2:
                                    primary, secondary = cand[0], cand[1]

            else:
                # label not found — leave both empty
                primary = ""
                secondary = ""

            # final cleanup (strip trailing numeric footers etc.)
            primary = re.sub(r"\b\d+\b\s*$", "", primary).strip()
            secondary = re.sub(r"\b\d+\b\s*$", "", secondary).strip()

            rows.append({"Parameter": label, "Primary": primary, "Secondary": secondary})

        # Build DataFrame, save Excel and return JSON
        df = pd.DataFrame(rows, columns=["Parameter", "Primary", "Secondary"])
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_cdr_link_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        duration = round(time.time() - start, 2)
        log_command("status cdr-link", "Success", excel_path, f"{len(df)} rows", duration)
        print(f"✅ Parsed {len(df)} rows → Excel: {excel_path}")

        return jsonify({"data": df.to_dict(orient="records"), "columns": df.columns.tolist(), "excel_path": excel_path})

    except Exception as e:
        print("❌ Error in status cdr-link:", e)
        log_command("status cdr-link", "Failed", None, str(e), 0)
        return jsonify({"error": str(e)}), 500


























# ======================================================
# Startup
# ======================================================
if __name__ == "__main__":
    init_command_log_db()
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        try:
            print("⚙️ Backend started — waiting for IP/password from frontend...")
            _cached_health_data = None

            print("✅ Startup health data ready.")
        except Exception as e:
            print(f"❌ Startup generation failed: {e}")
    app.run(host="0.0.0.0", port=5002, debug=True, use_reloader=False)

