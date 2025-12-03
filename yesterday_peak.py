import os
import re
import time
import string
import paramiko
import pandas as pd
from datetime import datetime

# ==============================
# SSH Configuration
# ==============================
# SAT_HOST = "172.16.70.39"
# SAT_PORT = 5022
# SAT_USERNAME = "dadmin"
# SAT_PASSWORD = "Avaya@123"

SAT_HOST = None
SAT_PORT = 5022
SAT_USERNAME = "dadmin"
SAT_PASSWORD = None

COMMAND = "list measurements trunk-group summary yesterday-peak"

# === IMPORTANT: absolute reports dir (backend expects this) ===
# ✅ new (relative)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# ==============================
# Utility Functions
# ==============================
def clean_output(output):
    """Remove ANSI escape codes and control characters."""
    output = re.sub(r'\x1B[@-_][0-?]*[ -/]*[@-~]', '', output)
    output = re.sub(r'(?m)^Command:.*$', '', output)
    output = re.sub(r'\r', '', output)
    output = re.sub(r'\n{2,}', '\n', output)
    output = ''.join(ch for ch in output if ch in string.printable or ch == '\n')
    return output.strip()

def auth_handler(title, instructions, prompt_list):
    return [SAT_PASSWORD if 'Password' in p[0] else '' for p in prompt_list]

# ==============================
# SSH Command Execution
# ==============================
# def run_avaya_command():
#     """
#     Connect to Avaya SAT, execute the yesterday-peak command,
#     and automatically fetch all pages (pressing F7 until done).
#     """
#     transport = paramiko.Transport((SAT_HOST, SAT_PORT))
#     transport.connect()
#     transport.auth_interactive(SAT_USERNAME, auth_handler)

#     channel = transport.open_session()
#     channel.get_pty()
#     channel.invoke_shell()
#     time.sleep(2)

#     # optional terminal type negotiation
#     if channel.recv_ready():
#         banner = channel.recv(4096).decode(errors='ignore')
#         if "Terminal Type" in banner:
#             channel.send("VT220\n")
#             time.sleep(1)
#             if channel.recv_ready():
#                 channel.recv(4096)

#     # enter SAT
#     channel.send("sat\n")
#     time.sleep(2)
#     if channel.recv_ready():
#         channel.recv(4096)

#     print(f"→ Executing: {COMMAND}")
#     channel.send(COMMAND + "\n")
#     time.sleep(3)

#     full_output = ""
#     page_counter = 1
#     idle_wait = 0.8  # seconds between reads

#     while True:
#         time.sleep(idle_wait)
#         page_data = ""
#         # read everything currently available
#         while channel.recv_ready():
#             chunk = channel.recv(16384).decode(errors="ignore")
#             page_data += chunk
#             time.sleep(0.05)

#         if not page_data.strip():
#             # no new data available — break the loop
#             break

#         full_output += page_data
#         print(f"   📄 Page {page_counter} captured ({len(page_data)} chars)")

#         # check for "press NEXT PAGE" prompt (case-insensitive)
#         if "press next page" in page_data.lower():
#             # emulate F7 key (go to next page)
#             channel.send("\x1b[18~")
#             page_counter += 1
#             # give SAT a moment to respond with next page
#             time.sleep(0.6)
#             continue
#         else:
#             # no more pages prompt — stop paging
#             break

#     transport.close()
#     print(f"✅ Total pages fetched: {page_counter}")
#     return clean_output(full_output)



def run_avaya_command(custom_command=None):
    """
    Connect to Avaya SAT, handle terminal type negotiation,
    then execute a given SAT command and fetch all pages.
    """
    import paramiko, time, re

    command_to_run = custom_command or COMMAND

    transport = paramiko.Transport((SAT_HOST, SAT_PORT))
    transport.connect()
    transport.auth_interactive(SAT_USERNAME, auth_handler)

    channel = transport.open_session()
    channel.get_pty()
    channel.invoke_shell()
    time.sleep(2)

    # --- Handle "Terminal Type" negotiation ---
    if channel.recv_ready():
        banner = channel.recv(4096).decode(errors='ignore')
        if "Terminal Type" in banner or "INVALID TERMINAL TYPE" in banner:
            print("⚙️ Negotiating terminal type...")
            # Send a valid type (VT220 is safest)
            channel.send("VT220\n")
            time.sleep(1)
            # Drain any follow-up prompts
            if channel.recv_ready():
                channel.recv(4096)

    # --- Enter SAT ---
    channel.send("sat\n")
    time.sleep(2)
    if channel.recv_ready():
        pre_sat = channel.recv(4096).decode(errors='ignore')
        if "Terminal Type" in pre_sat:
            print("⚙️ Re-negotiating terminal type (inside SAT)...")
            channel.send("VT220\n")
            time.sleep(1)
            if channel.recv_ready():
                channel.recv(4096)

    # --- Execute the command ---
    print(f"→ Executing: {command_to_run}")
    channel.send(command_to_run + "\n")
    time.sleep(3)

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

        # handle pagination
        if "press next page" in page_data.lower():
            channel.send("\x1b[18~")  # emulate F7
            page_counter += 1
            time.sleep(0.6)
        else:
            break

    transport.close()
    print(f"✅ Total pages fetched: {page_counter}")

    # 🛡 prevent None from ever being returned
    if not full_output.strip():
        print("⚠️ WARNING: SAT returned no data → returning empty string")
        return ""

    return clean_output(full_output)





def run_yesterday_peak(ip, password, custom_command=None):
    """
    Wrapper so UI can pass IP + password dynamically.
    
    """
    global SAT_HOST, SAT_PASSWORD, SAT_USERNAME

    SAT_HOST = ip
    SAT_PASSWORD = password
    SAT_USERNAME = "dadmin"

    # reuse the original function exactly as-is
    return run_avaya_command(custom_command)







# ==============================
# Parser
# ==============================
def parse_trunk_summary(output):

    if output is None:
        print("⚠️ parse_trunk_summary received None → converting to empty.")
        output = ""
    
    cols = [
        "Grp No", "Grp Siz", "Grp Type", "Grp Dir", "Meas Hour",
        "Total Usage", "Total Seize", "Inc. Seize", "Grp Ovfl",
        "Que Siz", "Call Qued", "Que Ovf", "Que Abd",
        "Out Srv", "%ATB", "%Blk"
    ]
    rows = []

    for line in output.splitlines():
        line = line.strip()
        if not re.match(r'^\d+', line):
            continue

        tokens = line.split()
        if len(tokens) < 8:
            continue

        # --- Fix merged 'sip two2300 0' patterns ---
        if len(tokens) >= 4 and re.match(r'^(sip|isdn)$', tokens[2]) and not re.match(r'^(two|one)$', tokens[3]):
            merged = re.findall(r'(sip|isdn)?(two|one)?(\d{3,4})?', tokens[3])
            merged = [m for tup in merged for m in tup if m]
            tokens = tokens[:2] + [tokens[2]] + merged + tokens[4:]

        # --- Smart numeric correction for Out Srv / %ATB / %Blk ---
        # Out Srv normally sits at index 13
        if len(tokens) >= 14:
            out_srv = tokens[13]
            # case: Out Srv = "1000" and row has no explicit %ATB yet
            if re.fullmatch(r'\d{4}', out_srv):
                if len(tokens) == 14:  # no %ATB or %Blk present yet
                    tokens[13] = out_srv[:3]        # Out Srv
                    tokens.insert(14, out_srv[3:])  # %ATB
                    tokens.append("0")              # %Blk
                else:
                    # Already has %ATB/%Blk, do not split again
                    pass
            elif re.fullmatch(r'\d{3}', out_srv):
                # three-digit Out Srv; ensure following cols exist
                while len(tokens) < 16:
                    tokens.append("0")

        # --- Ensure full 16 columns every time ---
        tokens += ["0"] * (len(cols) - len(tokens))
        rows.append(tokens[:len(cols)])

    df = pd.DataFrame(rows, columns=cols)

    if df.empty:
        df.loc[0] = ["No data parsed or output unavailable"] + [""] * (len(cols) - 1)

    return df

# ==============================
# Main Execution
# ==============================
def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # enforce the exact prefix used by the backend app.py glob pattern
    safe_prefix = "list_measurements_trunk-group_summary_yesterday-peak"
    excel_file = os.path.join(REPORT_DIR, f"{safe_prefix}_{timestamp}.xlsx")

    try:
        output = run_avaya_command()
        df = parse_trunk_summary(output)

        # --- Write to Excel with formatting ---
        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Trunk Summary", index=False)
            ws = writer.sheets["Trunk Summary"]

            # Style headers
            from openpyxl.styles import Font, Alignment
            bold = Font(bold=True)
            for cell in ws[1]:
                cell.font = bold
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Auto width
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value and len(str(cell.value)) > max_len:
                            max_len = len(str(cell.value))
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = max_len + 2

        print(f"\n✅ Excel report created successfully:\n{excel_file}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()