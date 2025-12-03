import os
import re
import time
import string
import paramiko
import openpyxl
from datetime import datetime
from openpyxl.styles import Font, Alignment

# ======================================================
# CONFIGURATION
# ======================================================
SAT_HOST = None
SAT_PORT = 5022
SAT_USERNAME = "dadmin"
SAT_PASSWORD = None

SSH_HOST = None
SSH_PORT = 22
SSH_USERNAME = "dadmin"
SSH_PASSWORD = None

EXCEL_PATH = os.path.join("backend", "latest_avaya_page_log.xlsx")
os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

# ======================================================
# COMMAND SETS
# ======================================================
sat_commands = [
    "status media-processor all",
    "list media-gateway",
    "list survivable-processor",
    "status aesvcs cti-link",
    "status processor-channels 3",
    "status processor-channels 5",
    "list measurements outage-trunk last-hour",
    "status aesvcs interface",
    "status aesvcs link",
    "status cdr-link",
]

linux_commands = [
    "/opt/ecs/bin/statapp",
    "date",
    "uptime",
    "df -h",
    "df -k",
    "cat /etc/hosts",
    "/opt/ecs/bin/almdisplay -v",
    "/opt/ecs/bin/statusserver",
    "/opt/ecs/sbin/backup -t",
]


# ======================================================
# UTILITIES
# ======================================================
def clean_output(output):
    """Remove control codes and nonprintable characters."""
    output = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", output)
    output = re.sub(r"(?m)^Command:.*$", "", output)
    output = "".join(ch for ch in output if ch in string.printable or ch == "\n")
    return output.strip()


def run_linux_command(ssh_client, cmd, timeout=15):
    """Run a Linux command via Paramiko with PTY and capture output."""
    stdin, stdout, stderr = ssh_client.exec_command(cmd, get_pty=True)
    chan = stdout.channel
    out, err = [], []
    start = time.time()
    last_recv = time.time()
    while True:
        while chan.recv_ready():
            out.append(chan.recv(4096).decode(errors="ignore"))
            last_recv = time.time()
        while chan.recv_stderr_ready():
            err.append(chan.recv_stderr(4096).decode(errors="ignore"))
            last_recv = time.time()
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break
        if time.time() - last_recv > timeout:
            break
        time.sleep(0.2)
    return clean_output("".join(out)), clean_output("".join(err))


def run_sat_commands(host, port, username, password, commands, timeout_per_cmd=10):
    """Run SAT interactive commands with VT220 negotiation."""
    results = {}
    transport = None
    try:
        # Establish transport without unsupported keyword
        transport = paramiko.Transport((host, port))
        transport.connect()  # no timeout arg here

        # authentication (interactive password)
        transport.auth_interactive(
            username,
            lambda t, i, p: [password if "Password" in x[0] else "" for x in p]
        )

        chan = transport.open_session()
        chan.get_pty()
        chan.invoke_shell()
        time.sleep(2)

        if chan.recv_ready():
            banner = chan.recv(8192).decode(errors="ignore")
            if "Terminal" in banner or "terminal" in banner:
                chan.send("VT220\n")
                time.sleep(1)
                if chan.recv_ready():
                    chan.recv(8192)

        # enter SAT mode
        chan.send("sat\n")
        time.sleep(2)
        if chan.recv_ready():
            chan.recv(8192)

        # run each command
        for cmd in commands:
            print(f"→ Running SAT command: {cmd}")
            chan.send(cmd + "\n")
            start = time.time()
            last_recv = time.time()
            buf = []
            while True:
                if chan.recv_ready():
                    chunk = chan.recv(8192).decode(errors="ignore")
                    buf.append(chunk)
                    last_recv = time.time()
                if time.time() - last_recv > 1.0 or time.time() - start > timeout_per_cmd:
                    break
                time.sleep(0.2)
            results[cmd] = clean_output("".join(buf))
            time.sleep(0.3)

        chan.close()
    finally:
        if transport:
            try:
                transport.close()
            except Exception:
                pass
    return results




import re

def parse_alarms_output(raw_text):
    alarms = []
    pattern = re.compile(
        r"ID:\s*(?P<ID>\S+)\s*"
        r"Source:\s*(?P<Source>\S+)\s*"
        r"EvtID:\s*(?P<EvtID>\S+)\s*"
        r"Level:\s*(?P<Level>\S+)\s*"
        r"Ack:\s*(?P<Ack>\S+)\s*"
        r"Date:\s*(?P<Date>[^\n]+)\s*"
        r"Description:\s*(?P<Description>.*?)(?=(?:\nID:|\Z))",
        re.DOTALL
    )

    for match in pattern.finditer(raw_text):
        alarm = match.groupdict()
        # Normalize level names
        level = alarm["Level"].strip().upper()
        if level.startswith("CRI"):
            alarm["Severity"] = "Critical"
        elif level.startswith("MAJ"):
            alarm["Severity"] = "Major"
        elif level.startswith("MIN"):
            alarm["Severity"] = "Minor"
        else:
            alarm["Severity"] = "Unknown"
        alarms.append(alarm)

    return alarms


import re

def parse_df_output(df_text):
    """
    Robust parser for 'df -h' or 'df -k'.
    Always returns a list of dicts:
      Filesystem | Size | Used | Avail | Use% | Mounted on
    """
    import re

    if not df_text.strip():
        return []

    lines = df_text.replace("\r\n", "\n").split("\n")
    lines = [l for l in lines if l.strip()]
    if len(lines) < 2:
        return []

    rows = []

    # skip header, parse each line
    for line in lines[1:]:
        # collapse whitespace, but keep mountpoint intact by maxsplit=5
        parts = re.split(r"\s+", line.strip(), maxsplit=5)
        if len(parts) < 6:
            # not a valid df row
            continue

        fs, size, used, avail, usep, mount = parts[:6]

        rows.append({
            "Filesystem": fs,
            "Size": size,
            "Used": used,
            "Avail": avail,
            "Use%": usep,
            "Mounted on": mount
        })

    return rows












# ======================================================
# MAIN EXECUTION
# ======================================================
def generate_health_data(ip=None, password=None):

    """
    Executes all Linux and SAT commands, writes to Excel,
    and returns a JSON-style dict with parsed metrics.
    """

        # ✅ Step 1: define fallback defaults
    SSH_USERNAME = "dadmin"
    SAT_USERNAME = "dadmin"
    
    # Only override SSH/SAT globals if values are provided.
    if ip:
        SSH_HOST = ip
        SAT_HOST = ip

    if password:
        SSH_PASSWORD = password
        SAT_PASSWORD = password
    



    print("🔹 Collecting live Linux + SAT data...")

    command_logs = []  # ✅ Collect each executed command for logging


    

    # workbook
    wb = openpyxl.Workbook()
    for s in wb.sheetnames:
        del wb[s]
    ws_linux = wb.create_sheet("Linux")
    ws_sat = wb.create_sheet("SAT")
    ws_linux.append(["Timestamp", "Command", "Output", "Error"])
    ws_sat.append(["Timestamp", "SAT Command", "Output"])

    # 1️⃣  Linux
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USERNAME, password=SSH_PASSWORD, timeout=10)

    linux_outputs = {}
    for cmd in linux_commands:
        start = time.time()
        print(f"→ Executing: {cmd}")
        out, err = run_linux_command(client, cmd)
        duration = time.time() - start

        # store output
        linux_outputs[cmd] = out or err
        ws_linux.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cmd, out, err])

        # ✅ Add command log entry
        summary = (out or err or "").splitlines()
        short_summary = summary[0][:200] if summary else ""
        command_logs.append({
            "command": cmd,
            "status": "Executed" if not err else "Failed",
            "duration": duration,
            "summary": short_summary
        })

    client.close()

    # 2️⃣  SAT
    sat_outputs = run_sat_commands(SAT_HOST, SAT_PORT, SAT_USERNAME, SAT_PASSWORD, sat_commands)
    for cmd, out in sat_outputs.items():
        ws_sat.append([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cmd, out])

        # ✅ Log SAT commands too
    for cmd, out in sat_outputs.items():
        command_logs.append({
            "command": cmd,
            "status": "Executed",
            "duration": 0.0,  # if you want, you can measure same as Linux above
            "summary": (out or "").splitlines()[0][:200] if out else ""
        })


    # 3️⃣  Style headers
    for ws in [ws_linux, ws_sat]:
        bold = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold
            cell.alignment = Alignment(horizontal="center")
        for col in ws.columns:
            max_len = max(len(str(c.value)) for c in col if c.value)
            ws.column_dimensions[col[0].column_letter].width = max_len + 3

    wb.save(EXCEL_PATH)
    print(f"✅ Excel saved to {EXCEL_PATH}")

    # 4️⃣  Build JSON-like return dict
    data = {}

    # Parse uptime
    uptime_out = linux_outputs.get("uptime", "")
    uptime_days = re.search(r"up\s+(\d+)\s+day", uptime_out)
    data["system_uptime"] = uptime_days.group(1) + " days" if uptime_days else "N/A"

    # Disk utilisation summary
    dfh_raw = linux_outputs.get("df -h", "")
    dfk_raw = linux_outputs.get("df -k", "")

    dfh_parsed = parse_df_output(dfh_raw)
    dfk_parsed = parse_df_output(dfk_raw)

    data["disk_utilisation"] = {
        "df -h": dfh_raw,          # raw multi-line text
        "df -h-list": dfh_parsed,  # parsed list for future
        "df -k": dfk_raw,
        "df -k-list": dfk_parsed
    }



    # Alarms, server status, backup
    data["alarms"] = linux_outputs.get("/opt/ecs/bin/almdisplay -v", "Unknown")
    data["server_status"] = linux_outputs.get("/opt/ecs/bin/statusserver", "Unknown")
    data["backup_status"] = linux_outputs.get("/opt/ecs/sbin/backup -t", "Unknown")

    data["command_logs"] = command_logs  # ✅ include logs in response
    return data



if __name__ == "__main__":
    info = generate_health_data()
    print("✅ Health data generated. Summary:")
    print(info)
