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
        yesterday_peak.SAT_USERNAME = "DCLWeb"


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




# Parser - CTI Link
def parse_cti_link(output):
    lines = output.splitlines()

    # Skip until header is detected
    start_idx = None
    for i, line in enumerate(lines):
        if re.search(r"CTI\s+Version\s+Mnt", line):
            start_idx = i + 2   # skip header + sub-header
            break

    if start_idx is None:
        return {"error": "Header not found", "data": []}

    rows = []
    row_re = re.compile(
        r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)"
    )

    for line in lines[start_idx:]:
        m = row_re.match(line)
        if not m:
            continue  # skip garbage / empty / footer

        row = {
            "CTI Link": m.group(1),
            "Version": m.group(2),
            "Mnt Busy": m.group(3),
            "AE Services Server": m.group(4),
            "Service State": m.group(5),
            "Msgs Sent": m.group(6),
            "Msgs Rcvd": m.group(7)
        }
        rows.append(row)

    return rows




@app.route("/get-status-aesvcs-cti-link", methods=["GET", "POST"])
def get_status_aesvcs_cti_link():
    """
    Runs 'status aesvcs cti-link' on Avaya, parses properly spaced output,
    saves Excel, and returns JSON.
    """
    import re
    import pandas as pd
    import os, time
    from datetime import datetime
    from flask import jsonify

    try:
        start = time.time()
        print("⚙️ Running Avaya command: status aesvcs cti-link")

        # --- SAFE SSH call wrapper (prevents NoneType crashes) ---
        try:
            output = run_avaya_command("status aesvcs cti-link")

        except Exception as ssh_err:
            print("⚠️ SSH/run_avaya_command raised:", ssh_err)
            output = None

        # If output is None or empty → return friendly no-data JSON (200)
        if not output or not isinstance(output, str) or output.strip() == "":
            print("ℹ️ status aesvcs cti-link returned no output or SAT did not respond.")
            os.makedirs("outputs", exist_ok=True)

            df = pd.DataFrame([{
                "Message": "No data in the system to list or SAT did not respond"
            }])

            excel_path = os.path.join("outputs", "status_aesvcs_cti_link_no_data.xlsx")
            df.to_excel(excel_path, index=False)

            log_command("status aesvcs cti-link", "Success", excel_path, "No data", 0)

            # Return UI-friendly shape (empty table but not an error)
            return jsonify({
                "data": [],
                "columns": ["Message"],
                "excel_path": excel_path,
                "note": "No data in the system to list or SAT did not respond"
            }), 200


        columns = [
            "CTI Link",
            "Version",
            "Mnt Busy",
            "AE Services Server",
            "Service State",
            "Msgs Sent",
            "Msgs Rcvd",
        ]

        # Build DataFrame exactly as before
        print("CTI link output is: ", output)
        df = pd.DataFrame(parse_cti_link(output=output), columns=columns)
        df = df.replace({pd.NA: None, pd.NaT: None, float("nan"): None})

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_aesvcs_cti_link{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        # ✅ Log success (keeps your exact logging signature)
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



# Parser - Survivable Processor
def parse_survivable_processor_output(output):

    if not output or not output.strip():
        return []

    cleaned_lines = []
    for line in output.splitlines():
        raw = line.rstrip()
        if not raw.strip():
            continue
        if "SURVIVABLE" in raw or "Record Name" in raw or re.search(r"Number\s+IP", raw):
            continue
        if "Command successfully" in raw or "press" in raw.lower():
            continue
        if re.search(r"Page\s+\d+", raw):
            continue
        if "CANCEL" in raw:
            continue
        cleaned_lines.append(raw)

    data_rows = []
    i = 0

    ip_re = re.compile(r"^\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})\s*$")

    # Primary regex (improved)
    primary_re = re.compile(
        r"^\s*(\d+)\s+(.+?)\s+([A-Z0-9\-]+)\s+([ynYN])\s+([ynYN])\s*(.*?)\s+(\d+)\s*$",
        re.IGNORECASE
    )

    while i < len(cleaned_lines):

        line = cleaned_lines[i].lstrip()
        m = primary_re.match(line)

        if m:
            rec_no = m.group(1).strip()
            name = m.group(2).strip()
            type_ = m.group(3).strip()
            reg = m.group(4).strip().lower()
            ack = m.group(5).strip().lower()
            translations = m.group(6).strip()
            net_rgn = m.group(7).strip()

            # Next line may be IP address
            ip_addr = ""
            notes = ""
            j = i + 1

            if j < len(cleaned_lines) and ip_re.match(cleaned_lines[j].strip()):
                ip_addr = ip_re.match(cleaned_lines[j].strip()).group(1)
                j += 1
                # optional note line ("No V6 Entry")
                if j < len(cleaned_lines) and not re.match(r"^\d+", cleaned_lines[j].strip()):
                    notes = cleaned_lines[j].strip()
                    j += 1

            row = {
                "Record number": rec_no,
                "Name/IP address": f"{name} {ip_addr}".strip(),
                "Type": type_,
                "Reg": reg,
                "Ack": ack,
                "Translations updated": translations,
                "Net Rgn": net_rgn
            }
            if notes:
                row["Name/IP address"] += f" ({notes})"

            data_rows.append(row)
            i = j
            continue

        # No match → skip
        i += 1

    return data_rows



  
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

        # --- Replace the call + early-check with this block inside get_list_survivable_processor_data ---

        try:
            # run command — guard against SSH exceptions or None returns
            try:
                output = run_avaya_command("list survivable-processor")
            except Exception as ssh_err:
                print("⚠️ SSH/run_avaya_command raised:", ssh_err)
                output = None

            # If output is missing or not a string → return a friendly no-data JSON (200)
            if not output or not isinstance(output, str) or output.strip() == "":
                print("ℹ️ list survivable-processor returned no output or SSH failed.")
                os.makedirs("outputs", exist_ok=True)
                # create a tiny no-data Excel so UI download still works
                df = pd.DataFrame([{"Message": "No data in the system to list or SAT did not respond"}])
                excel_path = os.path.join("outputs", "list_survivable_processor_no_data.xlsx")
                df.to_excel(excel_path, index=False)
                # Log as success (so command_logs reflect attempted run) but note 'No data'
                log_command("list survivable-processor", "Success", excel_path, "No data", 0)
                return jsonify({
                    "data": [],
                    "columns": ["Message"],
                    "excel_path": excel_path,
                    "note": "No data in the system to list or SAT did not respond"
                }), 200

        except Exception as e:
            # keep outer exception handling intact; will be caught by your route's outer try/except
            raise

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

        print("This is survivable processor output", output)
        df = pd.DataFrame(parse_survivable_processor_output(output=output), columns=columns)

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"list_survivable_processor_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

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


# 3 functions to parse Media gateways command

GATEWAY_CHUNK_RE = re.compile(r"\b(\d{1,3})\s+(\d+)\s+(\d+)\s+(\d+)\s+([A-Za-z]+)\b")


def extract_summary(text):
    """
    Extract top summary values (Major, Minor, Warning, Links Down, Links Up, Trunks, Stations, Logins).
    This is heuristic-based and tolerant to different label orders.
    """
    summary = {}
    # Common labels we try to capture
    patterns = {
        "Major": r"Major[:\s]+(\d+)",
        "Minor": r"Minor[:\s]+(\d+)",
        "Warning": r"Warning[:\s]+(\d+)",
        "Links Down": r"Links Down[:\s]+(\d+)",
        "Links Up": r"Links Up[:\s]+(\d+)",
        "Trunks": r"Trunks[:\s]+(\d+)",
        "Stations": r"Stations[:\s]+(\d+)",
        "Logins": r"Logins[:\s]+(\d+)"
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        summary[key] = int(m.group(1)) if m else None
    return summary


def parse_gateway_table(text):
    """
    Locate the 'GATEWAY STATUS' section and parse gateway rows.
    Each physical table row can contain up to 3 gateway chunks; we find all matches
    on each line and append them in order.
    """
    # Find the position of "GATEWAY STATUS"
    m = re.search(r"^\s*GATEWAY\s+STATUS\b", text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        # Try looser: look for a line that equals "GATEWAY STATUS" ignoring surrounding whitespace
        m = re.search(r"\bGATEWAY STATUS\b", text, flags=re.IGNORECASE)
    start_idx = m.end() if m else 0

    # Take the part after the "GATEWAY STATUS" header
    tail = text[start_idx:]

    # Remove any repeated header lines (lines that contain the header tokens)
    lines = []
    for line in tail.splitlines():
        if not line or line.strip().startswith("#"):
            # stop or skip comments
            continue
        # skip header-looking lines that contain the column names
        if re.search(r"\bMG\b|\bMjr\b|\bMnr\b|\bWng\b|\bLink\b", line, re.IGNORECASE):
            continue
        lines.append(line.rstrip())

    gateways = []
    for ln in lines:
        # Find all gateway chunks in this line (up to 3)
        for match in GATEWAY_CHUNK_RE.finditer(ln):
            mg, mjr, mnr, wng, link = match.groups()
            gateways.append({
                "MG": int(mg),
                "Major": int(mjr),
                "Minor": int(mnr),
                "Warning": int(wng),
                "Link": link.lower()
            })
    return gateways


def parse_status_media_gateways(sample_text):
    """
    High-level parser orchestrator.
    Returns dict { summary: {...}, gateways: [...] }
    """
    summary = extract_summary(sample_text)
    gateways = parse_gateway_table(sample_text)
    return {"summary": summary, "gateways": gateways}








@app.route("/get-status-media-gateway", methods=["GET", "POST"])
def get_status_media_gateway():
    import re
    import pandas as pd
    from flask import jsonify
    import os, time

    try:
        start = time.time()
        #output = run_avaya_command("status media-gateways")

        output = """
ALARM SUMMARY      |    BUSY-OUT SUMMARY       |   H.248 LINK SUMMARY
Major:  10         | Trunks: 180              | Links Down:  3     # Logins: 03
Minor:  9          | Stations:  9             | Links Up:    38
Warning: 720

GATEWAY STATUS

Alarms                       Alarms                      Alarms
MG  Mjr Mnr Wng Link   MG  Mjr Mnr Wng Link   MG  Mjr Mnr Wng Link
 1   0   2   3   up    2   1   0   1   up    3   0   1   1   up
 4   0   0   0   up    5   0   0   0   dn    6   2   1   0   up
 7   1   0   0   up    8   0   3   2   up    9   0   0   0   dn

# Sometimes the header repeats (should be skipped)
MG  Mjr Mnr Wng Link   MG  Mjr Mnr Wng Link   MG  Mjr Mnr Wng Link
10  0   0   0   up    11  0   1   0   up    12  1   0   0   up
13  0   0   0   dn    14  0   0   0   up

# End of table
"""

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
                #"summary": {},
                "data": [],
                "columns": [],
                "excel_path": excel_path,
                "note": "No data in the system to list"
            })

       

        print("This is media gateways output", output)

        # df = pd.DataFrame(parse_cdr_link_section(output=output), columns=columns)
        parsed = parse_status_media_gateways(output)  # get dict {summary, gateways}

        gateways = parsed["gateways"]  # <-- this is the actual list of gateway rows!

        summary = parsed["summary"]
        df_gateways = pd.DataFrame(gateways)

        # Optional: rename cols for UI preference
        df_gateways = df_gateways.rename(columns={
            "MG": "MG",
            "Major": "Mj",
            "Minor": "Mn",
            "Warning": "Wn",
            "Link": "Lk"
        })


        # --- Save Excel ---
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_media_gateway_{timestamp}.xlsx")

        df_gateways.to_excel(excel_path, index=False)

        # status_media_gateway

        log_command("status media-gateways", "Success", excel_path, f"{len(df_gateways)} gateways", 0)
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



#parser for status aesvcs link
ROW_RE = re.compile(
    r"^\s*(?P<svc_link>\S+)\s+"
    r"(?P<aes_server>\S+)\s+"
    r"(?P<remote_ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<remote_port>\d+)\s+"
    r"(?P<local_node>\S+)\s+"
    r"(?P<msgs_sent>\d+)\s+"
    r"(?P<msgs_rcvd>\d+)\s*$"
)

def parse_aesvcs_link(output):
    """
    Parse the 'status aesvcs link' output and return list of row dicts.
    Steps:
      - Normalize lines
      - Locate header line that begins with 'Svc/' (case-insensitive)
      - From next line parse lines that match ROW_RE until end or next header/footer
    """
    if not output:
        return []

    # Normalize CRLF and split
    lines = output.replace("\r\n", "\n").replace("\r", "\n").splitlines()

    # Find the header line that begins with 'Svc/' (skip everything until that)
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("svc/"):
            header_idx = i
            break

    if header_idx is None:
        # Try some fallback: look for 'Link  Server' or 'AE Services' header
        for i, ln in enumerate(lines):
            if "AE Services" in ln and "Remote IP" in ln:
                header_idx = i
                break

    # If still not found - nothing to parse
    if header_idx is None:
        return []

    # Data begins from the line after the header (skip header and header-underlines)
    start = header_idx + 1
    # Skip a possible second header line (like the "Link  Server" line). Move start forward
    # until we hit a line that looks like data (starts with a token like NN/NN or digits)
    while start < len(lines):
        test = lines[start].strip()
        # break if test looks like a data row start (e.g. "12/01" or "9/08" or similar)
        if re.match(r"^\d+/\d+\b", test) or ROW_RE.match(test):
            break
        start += 1

    parsed = []
    for ln in lines[start:]:
        s = ln.strip()
        if not s:
            continue
        # stop on page/footer markers
        low = s.lower()
        if low.startswith("press") or low.startswith("page") or low.startswith("#") or "command" in low:
            continue
        m = ROW_RE.match(s)
        if m:
            parsed.append({
                "svc_link": m.group("svc_link"),
                "aes_server": m.group("aes_server"),
                "remote_ip": m.group("remote_ip"),
                "remote_port": int(m.group("remote_port")),
                "local_node": m.group("local_node"),
                "msgs_sent": int(m.group("msgs_sent")),
                "msgs_rcvd": int(m.group("msgs_rcvd")),
            })
        else:
            # not matched — sometimes server names contain dashes or other chars, or remote_ip might be missing.
            # attempt a more permissive parse: split tokens and try to map expected fields
            # tokenization fallback:
            toks = re.split(r"\s+", s)
            # require at least 7 tokens for fallback
            if len(toks) >= 7:
                # last two tokens are msgs_sent and msgs_rcvd if they are digits
                if toks[-1].isdigit() and toks[-2].isdigit():
                    msgs_rcvd = int(toks[-1])
                    msgs_sent = int(toks[-2])
                    local_node = toks[-3]
                    remote_port = toks[-4]
                    remote_ip = toks[-5]
                    aes_server = toks[-6]
                    svc_link = toks[-7]
                    # only accept if remote_ip looks like IP and remote_port digits
                    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", remote_ip) and remote_port.isdigit():
                        parsed.append({
                            "svc_link": svc_link,
                            "aes_server": aes_server,
                            "remote_ip": remote_ip,
                            "remote_port": int(remote_port),
                            "local_node": local_node,
                            "msgs_sent": msgs_sent,
                            "msgs_rcvd": msgs_rcvd,
                        })
                    else:
                        # otherwise skip
                        continue
                else:
                    continue
            else:
                continue

    return parsed










@app.route("/get-status-aesvcs-link", methods=["GET", "POST"])
def get_status_aesvcs_link():
    import re
    import pandas as pd
    import os, time

    try:
        start = time.time()
        print("⚙️ Running Avaya command: status aesvcs link")

        output = run_avaya_command("status aesvcs link")

        if not output or len(output.strip()) == 0:
            return jsonify({"error": "No output from Avaya command"}), 500

        columns = [
            "Srvr/Link",
            "AE Services Server",
            "Remote IP",
            "Remote Port",
            "Local Node",
            "Msgs Sent",
            "Msgs Rcvd",
        ]

        # 🔥 FIX — rename dict keys to match UI column names
        raw_rows = parse_aesvcs_link(output)
        mapped_rows = [
            {
                "Srvr/Link": r["svc_link"],
                "AE Services Server": r["aes_server"],
                "Remote IP": r["remote_ip"],
                "Remote Port": r["remote_port"],
                "Local Node": r["local_node"],
                "Msgs Sent": r["msgs_sent"],
                "Msgs Rcvd": r["msgs_rcvd"],
            }
            for r in raw_rows
        ]

        df = pd.DataFrame(mapped_rows, columns=columns)

        # Save Excel
        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_aesvcs_link_{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

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







# parser - CDR Link
def parse_cdr_link_section(output):
    start = time.time()

    # Normalize spacing but keep long gaps that indicate column gap
    section = output or ""
    section = section.replace("\t", " ")
    section = re.sub(r"\r\n", "\n", section)
    # collapse repeated blank lines to single newline
    section = re.sub(r"\n{2,}", "\n\n", section).strip()

    # Remove footer/noise tokens (keep content safe)
    section = re.sub(r"(?i)press\s+CANCEL.*", "", section)
    section = re.sub(r"(?i)command\s+successfully.*", "", section)
    section = section.strip()

    expected = [
        "Link State",
        "Date & Time",
        "Forward Seq. No",
        "Backward Seq. No",
        "CDR Buffer % Full",
        "Reason Code"
    ]

    # Find positions of each label so we can extract the chunk reliably
    positions = {}
    for label in expected:
        m = re.search(re.escape(label) + r"\s*:", section, re.IGNORECASE)
        positions[label] = m.start() if m else -1

    present = [(lbl, pos) for lbl, pos in positions.items() if pos >= 0]
    if not present:
        raise ValueError("Could not detect expected labels in CDR LINK STATUS output")

    present.sort(key=lambda x: x[1])

    # Extract chunk for each label (text from label to next label)
    label_chunks = {}
    for i, (label, pos) in enumerate(present):
        start_pos = pos
        end_pos = present[i+1][1] if i+1 < len(present) else len(section)
        chunk = section[start_pos:end_pos].strip()
        # remove the label and colon
        chunk = re.sub(re.escape(label) + r"\s*:\s*", "", chunk, flags=re.IGNORECASE).strip()
        label_chunks[label] = chunk

    # Now for each chunk normalize internal whitespace and split by multiple spaces as column separator
    def split_primary_secondary(chunk_text):
        """
        Return (primary, secondary) from a chunk.
        Approach:
          - Replace newlines with single space
          - Replace runs of 2+ spaces with a separator token '|||'
          - Split on token: left -> primary, right -> secondary (strip)
        """
        if not chunk_text or chunk_text.strip() == "":
            return "", ""
        # collapse internal multiple newlines/spaces, but preserve "2+ spaces" boundary
        one_line = re.sub(r"\s*\n\s*", " ", chunk_text).strip()
        # replace repeated spaces (2 or more) with a token
        tokened = re.sub(r" {2,}", " ||| ", one_line)
        parts = [p.strip() for p in tokened.split("|||")]
        # parts may have surrounding separators; clean them
        parts = [p for p in parts if p is not None]
        # After split, primary should be first non-empty, secondary the next non-empty
        primary = parts[0].strip() if len(parts) >= 1 else ""
        secondary = parts[1].strip() if len(parts) >= 2 else ""
        return primary, secondary

    rows = []
    for label in expected:
        chunk = label_chunks.get(label, "")
        primary, secondary = split_primary_secondary(chunk)
        # Final cleanups
        primary = primary.strip()
        secondary = secondary.strip()
        rows.append({"Parameter": label, "Primary": primary, "Secondary": secondary})

    df = pd.DataFrame(rows, columns=["Parameter", "Primary", "Secondary"])
    duration = round(time.time() - start, 2)
    return rows



@app.route("/get-status-cdr-link", methods=["GET", "POST"])
def get_status_cdr_link():
    import re
    import pandas as pd
    import os, time
    from flask import jsonify

    try:
        start = time.time()

        # --- RUN AVAYA COMMAND SAFELY ---
        try:
            output = run_avaya_command("status cdr-link")
    
        except Exception as ee:
            print("⚠️ SSH / run_avaya_command raised:", ee)
            output = None

        # --- NO DATA / SSH FAILURE FALLBACK ---
        if not output or not isinstance(output, str) or output.strip() == "":
            print("ℹ️ No SAT output for status cdr-link.")

            df = pd.DataFrame([{
                "Message": "No data in the system to list or SAT did not respond"
            }])

            os.makedirs("outputs", exist_ok=True)
            today_folder = datetime.now().strftime("%Y-%m-%d")
            out_dir = os.path.join("outputs", today_folder)
            os.makedirs(out_dir, exist_ok=True)

            excel_path = os.path.join(out_dir, "status_cdr_link_no_data.xlsx")
            df.to_excel(excel_path, index=False)

            log_command("status cdr-link", "Success", excel_path, "No data", 0)

            return jsonify({
                "data": [],
                "columns": ["Message"],
                "excel_path": excel_path,
                "note": "No data in the system to list or SAT did not respond"
            }), 200

        # ----------------------------------------------------------------------
        # 📌 USE THE NEW ROBUST PARSER (same logic as test_status_cdr_link_fixed.py)
        # ----------------------------------------------------------------------

        print("Output is",parse_cdr_link_section(output))
        columns = ["Parameter", "Primary", "Secondary"]
        df = pd.DataFrame(parse_cdr_link_section(output=output), columns=columns)

        os.makedirs("outputs", exist_ok=True)
        today_folder = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(os.path.join("outputs", today_folder), exist_ok=True)
        timestamp = datetime.now().strftime("%H-%M-%S")
        excel_path = os.path.join("outputs", today_folder, f"status_cdr_link{timestamp}.xlsx")

        df.to_excel(excel_path, index=False)

        duration = round(time.time() - start, 2)
        log_command("status cdr-link", "Success", excel_path, f"{len(df)} rows", duration)

        print(f"✅ Parsed {len(df)} cdr link rows → Excel: {excel_path}")
        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": columns,
            "excel_path": excel_path
        })

    except Exception as e:
        print(f"❌ Error in cdr link: {e}")
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

