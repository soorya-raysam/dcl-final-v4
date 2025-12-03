#!/usr/bin/env python3
import os
import re
import time
import string
import paramiko
import pandas as pd
from datetime import datetime
from openpyxl.styles import Font, Alignment
from openpyxl import load_workbook

# ==============================
# SSH Configuration (dynamic-friendly defaults)
# ==============================
SAT_HOST = None          # will be injected via wrapper
SAT_PORT = 5022
SAT_USERNAME = "dadmin"
SAT_PASSWORD = None      # will be injected via wrapper
COMMAND = "status trunk 1"  # placeholder, can be overridden by caller

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ==============================
# Utilities
# ==============================
def clean_output(output):
    """Remove ANSI escape codes and control characters."""
    output = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", output)
    output = re.sub(r"[\r\b\f]", "", output)
    output = "".join(ch for ch in output if ch in string.printable or ch == "\n")
    output = re.sub(r"\n{2,}", "\n", output)
    return output.strip()

def auth_handler(title, instructions, prompt_list):
    return [SAT_PASSWORD if "Password" in p[0] else "" for p in prompt_list]

# ==============================
# Core SSH Runner (re-usable)
# ==============================
def run_avaya_command(custom_command=None):
    """
    Connect to Avaya SAT, handle terminal type negotiation,
    then execute a given SAT command and fetch all pages.
    Returns cleaned text output.
    """
    command_to_run = custom_command or COMMAND

    # Use paramiko Transport + auth_interactive to mimic existing behaviour
    transport = paramiko.Transport((SAT_HOST, SAT_PORT))
    transport.connect()
    transport.auth_interactive(SAT_USERNAME, auth_handler)

    channel = transport.open_session()
    channel.get_pty()
    channel.invoke_shell()
    time.sleep(2)

    # --- Handle "Terminal Type" negotiation ---
    if channel.recv_ready():
        banner = channel.recv(4096).decode(errors="ignore")
        if "Terminal Type" in banner or "INVALID TERMINAL TYPE" in banner:
            # print("⚙️ Negotiating terminal type...")
            channel.send("VT220\n")
            time.sleep(1)
            if channel.recv_ready():
                channel.recv(4096)

    # --- Enter SAT ---
    channel.send("sat\n")
    time.sleep(2)
    if channel.recv_ready():
        pre_sat = channel.recv(4096).decode(errors="ignore")
        if "Terminal Type" in pre_sat:
            # print("⚙️ Re-negotiating terminal type (inside SAT)...")
            channel.send("VT220\n")
            time.sleep(1)
            if channel.recv_ready():
                channel.recv(4096)

    # --- Execute the command ---
    print(f"→ Executing: {command_to_run}")
    channel.send(command_to_run + "\n")
    time.sleep(2)

    full_output = ""
    page_counter = 1
    idle_wait = 0.8

    while True:
        time.sleep(idle_wait)
        page_data = ""
        while channel.recv_ready():
            chunk = channel.recv(16384).decode(errors="ignore")
            page_data += chunk
            time.sleep(0.05)

        if not page_data.strip():
            break

        full_output += page_data
        print(f"   📄 Page {page_counter} captured ({len(page_data)} chars)")

        # --- Pagination handling (press next page) ---
        if "press next page" in page_data.lower():
            channel.send("\x1b[18~")  # emulate F7 key
            page_counter += 1
            time.sleep(0.6)
        else:
            break

    transport.close()
    print(f"✅ Total pages fetched: {page_counter}")
    return clean_output(full_output)







from concurrent.futures import ThreadPoolExecutor, as_completed

def run_status_single(ip, password, grp, timeout=30):
    """
    Run 'status trunk <grp>' on the given IP using its own Transport/session.
    Returns cleaned output string or '' on error.
    This does NOT touch module-level SAT_HOST / SAT_PASSWORD so it's thread-safe.
    """
    try:
        def local_auth_handler(title, instructions, prompt_list):
            return [password if "Password" in p[0] else "" for p in prompt_list]

        transport = paramiko.Transport((ip, SAT_PORT))
        transport.connect()
        transport.auth_interactive(SAT_USERNAME, local_auth_handler)

        channel = transport.open_session()
        channel.get_pty()
        channel.invoke_shell()
        time.sleep(1)

        # negotiate terminal type if requested
        if channel.recv_ready():
            banner = channel.recv(4096).decode(errors="ignore")
            if "Terminal Type" in banner or "INVALID TERMINAL TYPE" in banner:
                channel.send("VT220\n")
                time.sleep(0.5)
                if channel.recv_ready():
                    channel.recv(4096)

        channel.send("sat\n")
        time.sleep(1)
        if channel.recv_ready():
            pre = channel.recv(4096).decode(errors="ignore")
            if "Terminal Type" in pre:
                channel.send("VT220\n")
                time.sleep(0.5)
                if channel.recv_ready():
                    channel.recv(4096)

        cmd = f"status trunk {grp}"
        channel.send(cmd + "\n")
        time.sleep(1)

        full_output = ""
        page_counter = 1
        idle_wait = 0.6

        while True:
            time.sleep(idle_wait)
            page_data = ""
            while channel.recv_ready():
                chunk = channel.recv(16384).decode(errors="ignore")
                page_data += chunk
                time.sleep(0.03)

            if not page_data.strip():
                break

            full_output += page_data
            # pagination
            if "press next page" in page_data.lower():
                channel.send("\x1b[18~")
                page_counter += 1
                time.sleep(0.4)
            else:
                break

        try:
            transport.close()
        except Exception:
            pass

        return clean_output(full_output)
    except Exception as e:
        print(f"[run_status_single] error for grp {grp}: {e}")
        return ""















# ==============================
# Parsers
# ==============================
def parse_list_trunk_group(output):
    """Extract trunk group numbers from 'list trunk-group' output reliably."""
    cleaned = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.search(r"grp\s+name|group\s+type|Command|press", line, re.IGNORECASE):
            continue
        if re.match(r"^\d+", line):  # starts with number
            cleaned.append(line)

    groups = []
    for line in cleaned:
        # split safely on whitespace
        tokens = re.split(r"\s+", line)
        if tokens and tokens[0].isdigit():
            groups.append(int(tokens[0]))

    print(f"📋 Found {len(groups)} trunk groups: {groups}")
    return groups

def parse_status_trunk(output):
    """
    Parse 'status trunk' output into rows.
    This logic preserves your original behaviour and column names.
    """
    # preserve small adjustments you had previously
    output = output.replace("Service State      Mtce", "Service State   Mtce Busy")
    output = re.sub(r"[<>]\d+", "", output)

    # Look for lines that start with the Member pattern you used earlier
    # fallback: gather any lines containing pattern 'dddd/ddddT<port>'
    lines = []
    for l in output.splitlines():
        s = l.strip()
        if re.search(r"\d{4}/\d{4}T\d+", s):
            lines.append(s)

    rows = []
    for line in lines:
        m = re.match(
            r"(?P<Member>\d{4}/\d{4})T(?P<Port>\d+)\s+(?P<ServiceState>[A-Za-z0-9/\-]+)\s+(?P<MtceBusy>\w+)",
            line
        )
        if m:
            rows.append({
                "Member": m.group("Member"),
                "Port": f"T{m.group('Port')}",
                "Service State": m.group("ServiceState"),
                "Mtce Busy": m.group("MtceBusy"),
                "Connected Ports": ""
            })
    df = pd.DataFrame(rows, columns=["Member", "Port", "Service State", "Mtce Busy", "Connected Ports"])
    return df

# ==============================
# UI wrappers (Option A) — dynamic IP/password friendly
# ==============================
def run_status_trunk(ip, password, trunk):
    """
    Minimal wrapper to run 'status trunk <trunk>'.
    Returns raw cleaned output string (so caller may parse it).
    """
    global SAT_HOST, SAT_PASSWORD, SAT_USERNAME
    SAT_HOST = ip
    SAT_PASSWORD = password
    SAT_USERNAME = "dadmin"
    return run_avaya_command(f"status trunk {trunk}")



def load_groups_from_fixed_csv():
    """
    Load trunk groups from your fixed hardcoded CSV used by list trunk-group.
    CSV path: reports/report_list_trunk-group.csv
    Returns: list of integers
    """
    csv_path = os.path.join(REPORT_DIR, "report_list_trunk-group.csv")

    if not os.path.exists(csv_path):
        print(f" No fixed trunk-group file found: {csv_path}")
        return []

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print("Failed to read:", e)
        return []

    # Find the trunk group column (your previous file uses 2 columns)
    col = None
    for c in df.columns:
        # look for numeric-only values column
        if df[c].astype(str).str.match(r"^\d+$").any():
            col = c
            break

    if col is None:
        print("No numeric column found for trunk groups")
        return []

    groups = []
    for v in df[col].values:
        if pd.isna(v):
            continue
        try:
            groups.append(int(str(v).strip()))
        except:
            pass

    groups = sorted(list(set(groups)))
    print("Loaded trunk groups:", groups)
    return groups









def run_status_trunk_all(ip, password):
    """
    Wrapper which reproduces the behaviour of main():
    - runs 'list trunk-group'
    - for each trunk runs 'status trunk <grp>'
    - parses each result and writes a combined Excel
    Returns the created excel file path.
    """
    global SAT_HOST, SAT_PASSWORD, SAT_USERNAME
    SAT_HOST = ip
    SAT_PASSWORD = password
    SAT_USERNAME = "dadmin"

    print("🔍 Loading trunk group list...")
    trunk_groups = load_groups_from_fixed_csv()

    if not trunk_groups:
        print("⚠️ No trunk groups found.")
        return None


        # --- Concurrent fetcher ---
    all_dataframes = []
    max_workers = min(12, max(4, len(trunk_groups)))  # tune as needed
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run_status_single, SAT_HOST if SAT_HOST else ip, SAT_PASSWORD if SAT_PASSWORD else password, grp): grp for grp in trunk_groups}

        for fut in as_completed(futures):
            grp = futures[fut]
            try:
                out = fut.result()
                if not out:
                    print(f"⚠️ Empty output for trunk group {grp}")
                    continue
                df = parse_status_trunk(out)
                if not df.empty:
                    df.insert(0, "Trunk Group", grp)
                    all_dataframes.append(df)
                else:
                    print(f"⚠️ No data parsed for trunk group {grp}")
            except Exception as e:
                print(f"❌ Exception while fetching/parsing grp {grp}: {e}")


    # all_dataframes = []
    # for grp in trunk_groups:
    #     print(f"\n📡 Fetching status for trunk group {grp}...")
    #     out = run_avaya_command(f"status trunk {grp}")
    #     df = parse_status_trunk(out)
    #     if not df.empty:
    #         df.insert(0, "Trunk Group", grp)
    #         all_dataframes.append(df)
    #     else:
    #         print(f"⚠️ No data parsed for trunk group {grp}")

    if not all_dataframes:
        print("⚠️ No data collected for any trunk group.")
        return None

    final_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"✅ Combined {len(trunk_groups)} trunk group reports ({len(final_df)} total rows).")

    # --- Excel output (same naming as before) ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_file = os.path.join(REPORT_DIR, f"status_trunk_all_{timestamp}.xlsx")

    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        final_df.to_excel(writer, sheet_name="Status_Trunks", index=False)
        ws = writer.sheets["Status_Trunks"]

        bold = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            try:
                max_len = max(len(str(cell.value)) for cell in col if cell.value)
            except Exception:
                max_len = 10
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    print(f"\n✅ Excel report created successfully:\n{os.path.abspath(excel_file)}")
    return os.path.abspath(excel_file)











    

# ==============================
# Main Orchestrator (unchanged behaviour)
# ==============================
def main():
    print("🔍 Loading trunk group list...")
    trunk_groups = load_groups_from_fixed_csv()

    if not trunk_groups:
        print("⚠️ No trunk groups found.")
        return

    all_dataframes = []
    for grp in trunk_groups:
        print(f"\n📡 Fetching status for trunk group {grp}...")
        output = run_avaya_command(f"status trunk {grp}")
        df = parse_status_trunk(output)

        if not df.empty:
            df.insert(0, "Trunk Group", grp)
            all_dataframes.append(df)
        else:
            print(f"⚠️ No data parsed for trunk group {grp}")

    if not all_dataframes:
        print("⚠️ No data collected for any trunk group.")
        return

    final_df = pd.concat(all_dataframes, ignore_index=True)
    print(f"✅ Combined {len(trunk_groups)} trunk group reports ({len(final_df)} total rows).")

    # --- Excel output ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_file = os.path.join(REPORT_DIR, f"status_trunk_all_{timestamp}.xlsx")

    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        final_df.to_excel(writer, sheet_name="Status_Trunks", index=False)
        ws = writer.sheets["Status_Trunks"]

        bold = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            try:
                max_len = max(len(str(cell.value)) for cell in col if cell.value)
            except Exception:
                max_len = 10
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    print(f"\n✅ Excel report created successfully:\n{os.path.abspath(excel_file)}")

# ==============================
# Exports for importers
# ==============================
# Functions available for import:
# - run_status_trunk(ip, password, trunk) -> raw command output
# - run_status_trunk_all(ip, password) -> excel path (same behaviour as main)
# - parse_status_trunk(output) -> dataframe parse
# - parse_list_trunk_group(output) -> list of trunk numbers

# Keep running as a script preserving original behavior
if __name__ == "__main__":
    main()
