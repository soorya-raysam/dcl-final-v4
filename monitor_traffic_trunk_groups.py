#!/usr/bin/env python3
import os
import re
import time
import string
import paramiko
import pandas as pd
from datetime import datetime
from openpyxl.styles import Font, Alignment

# ==============================
# SSH Configuration (same as others)
# ==============================
SAT_HOST = None
SAT_PORT = 5022
SAT_USERNAME = "dadmin"
SAT_PASSWORD = None
COMMAND = "monitor traffic trunk-groups"

# Relative backend reports dir (changed from absolute to relative)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ==============================
# Utilities
# ==============================
def clean_output(output):
    output = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", output)
    output = re.sub(r"(?m)^Command:.*$", "", output)
    output = re.sub(r"\r", "", output)
    output = re.sub(r"\n{2,}", "\n", output)
    output = "".join(ch for ch in output if ch in string.printable or ch == "\n")
    return output.strip()

def auth_handler(title, instructions, prompt_list):
    return [SAT_PASSWORD if "Password" in p[0] else "" for p in prompt_list]

# ==============================
# SSH command with paging (F7)
# ==============================
def run_avaya_command(custom_command=None):
    """
    Note: changed to accept an optional custom_command parameter.
    Added handling for INVALID TERMINAL TYPE banner.
    """
    command_to_run = custom_command or COMMAND

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Connecting to {SAT_HOST}:{SAT_PORT} ...")
    client.connect(
        hostname=SAT_HOST,
        port=SAT_PORT,
        username=SAT_USERNAME,
        password=SAT_PASSWORD,
        look_for_keys=False,
        allow_agent=False,
        banner_timeout=20,
        timeout=30
    )

    channel = client.invoke_shell()  # no term param; CM will ask explicitly
    time.sleep(2)

    # --- detect terminal type prompt ---
    banner = ""
    if channel.recv_ready():
        banner = channel.recv(8192).decode(errors="ignore")
        print("=== RAW BANNER START ===")
        print(banner.strip())
        print("=== RAW BANNER END ===")

    # --- Handle INVALID TERMINAL TYPE or Terminal Type prompt ---
    if "INVALID TERMINAL TYPE" in banner or "Terminal Type" in banner:
        print("➡️ Sending VT220 terminal type...")
        channel.send("VT220\n")
        time.sleep(2)
        if channel.recv_ready():
            _ = channel.recv(4096).decode(errors="ignore")

    # --- Enter SAT shell ---
    channel.send("sat\n")
    time.sleep(2)
    if channel.recv_ready():
        sat_banner = channel.recv(4096).decode(errors="ignore")
        # Handle if CM re-prompts for terminal type again inside SAT
        if "Terminal Type" in sat_banner or "INVALID TERMINAL TYPE" in sat_banner:
            print("⚙️ Re-sending VT220 terminal type inside SAT...")
            channel.send("VT220\n")
            time.sleep(2)
            if channel.recv_ready():
                _ = channel.recv(4096).decode(errors="ignore")

    print(f"→ Executing: {command_to_run}")
    channel.send(command_to_run + "\n")
    time.sleep(2)

    full_output = ""
    while True:
        time.sleep(0.5)
        if channel.recv_ready():
            chunk = channel.recv(16384).decode(errors="ignore")
            full_output += chunk
            if "press next page" in chunk.lower() or "press any key to continue" in chunk.lower():
                channel.send("\x1b[18~")
                continue
        else:
            break

    client.close()
    print("✅ Command completed, output captured.")
    return clean_output(full_output)


# ==============================
# Parser - simple generic table parser
# ==============================
def parse_monitor_traffic_output(output):
    """
    Parse monitor traffic trunk-groups output into rows of (# S A Q W).
    Handles single-line or paginated CM output.
    """
    # Clean and normalize spacing
    txt = re.sub(r'\s+', ' ', output)
    # Force newlines before every trunk-group block (5 numbers in a row)
    txt = re.sub(r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', r'\n\1 \2 \3 \4 \5', txt)

    # Remove obvious headers/footers
    txt = re.sub(r'monitor traffic trunk-groups', '', txt, flags=re.I)
    txt = re.sub(r'TRUNK GROUP STATUS.*?WED|TUE|THU|FRI|SAT|SUN|MON', '', txt, flags=re.I)
    txt = re.sub(r'\(#:.*?\)', '', txt)

    # Extract (# S A Q W) tuples
    pattern = r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)'
    matches = re.findall(pattern, txt)
    if not matches:
        return pd.DataFrame([{"Message": "No trunk-group data parsed"}])

    records = [{"#": int(a), "S": int(b), "A": int(c), "Q": int(d), "W": int(e)} for a, b, c, d, e in matches]
    df = pd.DataFrame(records, columns=["#", "S", "A", "Q", "W"])
    
    return df


# ==============================
# UI wrapper (Option A) - minimal and non-invasive
# ==============================
def run_monitor_traffic_trunk_groups(ip, password, custom_command=None):
    """
    
    Leaves ALL existing logic untouched.
    """
    global SAT_HOST, SAT_PASSWORD, SAT_USERNAME

    SAT_HOST = ip
    SAT_PASSWORD = password
    SAT_USERNAME = "dadmin"

    return run_avaya_command(custom_command)


# ==============================
# Main
# ==============================
def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "monitor_traffic_trunk-groups"
    excel_path = os.path.join(REPORT_DIR, f"{prefix}_{timestamp}.xlsx")

    try:
        print("⚙️ Executing monitor traffic trunk-groups, please wait...")
        raw = run_avaya_command(COMMAND)
        print("\n=== RAW OUTPUT PREVIEW ===")
        print(raw[:1000])
        print("=== END PREVIEW ===\n")

        df = parse_monitor_traffic_output(raw)

        if df is None or df.empty:
            df = pd.DataFrame([{"Message": "No data parsed or output unavailable"}])

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Monitor_Traffic_Trunk_Groups", index=False)
            ws = writer.sheets["Monitor_Traffic_Trunk_Groups"]

            try:
                bold = Font(bold=True)
                for cell in ws[1]:
                    cell.font = bold
                    cell.alignment = Alignment(horizontal="center", vertical="center")
            except Exception:
                pass

            try:
                for col in ws.columns:
                    max_len = 0
                    col_letter = col[0].column_letter
                    for cell in col:
                        try:
                            if cell.value is not None:
                                l = len(str(cell.value))
                                if l > max_len:
                                    max_len = l
                        except Exception:
                            pass
                    ws.column_dimensions[col_letter].width = max_len + 2
            except Exception:
                pass

        print(f"✅ Excel created: {excel_path}")
    except Exception as e:
        print(f"❌ Error: {e}")
        fallback = os.path.join(REPORT_DIR, f"{prefix}_error_{timestamp}.xlsx")
        try:
            pd.DataFrame([{"Error": str(e)}]).to_excel(fallback, index=False, sheet_name="Monitor_Traffic_Trunk_Groups")
            print(f"⚠️ Error Excel created: {fallback}")
        except Exception as ex:
            print(f"⚠️ fallback write failed: {ex}")

if __name__ == "__main__":
    main()
