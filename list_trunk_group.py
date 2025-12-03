import os
import re
import time
import string
import paramiko
import pandas as pd
from datetime import datetime
from openpyxl.styles import Font, Alignment

# ==============================
# SSH CONFIGURATION
# ==============================
SAT_HOST = None
SAT_PORT = 5022
SAT_USERNAME = "dadmin"
SAT_PASSWORD = None
COMMAND = "list trunk-group"

# ==============================
# PATH CONFIGURATION (relative)
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# ==============================
# Utility Functions
# ==============================
def clean_output(output):
    """Remove ANSI escape codes and control characters."""
    output = re.sub(r"\x1B[@-_][0-?]*[ -/]*[@-~]", "", output)
    output = re.sub(r"(?m)^Command:.*$", "", output)
    output = re.sub(r"\r", "", output)
    output = re.sub(r"\n{2,}", "\n", output)
    output = "".join(ch for ch in output if ch in string.printable or ch == "\n")
    return output.strip()


def auth_handler(title, instructions, prompt_list):
    return [SAT_PASSWORD if "Password" in p[0] else "" for p in prompt_list]


# ==============================
# SSH Command Execution
# ==============================
def run_avaya_command(custom_command=None):
    """
    Connect to Avaya SAT, handle terminal type negotiation,
    then execute a given SAT command and fetch all pages.
    """

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
        banner = channel.recv(4096).decode(errors="ignore")
        if "Terminal Type" in banner or "INVALID TERMINAL TYPE" in banner:
            print("⚙️ Negotiating terminal type...")
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



# ==============================
# Parser (accurate version)
# ==============================
def parse_list_trunk_group(output):
    """
    Fully generalized parser for 'list trunk-group' via SSH.
    Handles variable Meas values (ext/int/both/none) and unpacks merged tails dynamically.
    """
    columns = [
        "Grp No",
        "TAC",
        "Group Type",
        "Group Name",
        "Mem",
        "TN",
        "COR",
        "CDR",
        "Meas",
        "Dsp",
        "Len",
    ]
    records = []

    for line in output.splitlines():
        line = line.strip()
        

        # Skip headers, prompts, or empty lines
        if (
            not line
            or line.startswith("list trunk-group")
            or "TRUNK GROUPS" in line
            or ("Grp" in line and "Group Name" in line)
            or "press CANCEL" in line
            or "Page" in line
            or "Command successfully" in line
        ):
            continue

        # Match real trunk-group data rows
        if re.search(r"\b\d+\s+#?\d+\s+(sip|isdn)\b", line):
            tokens = line.split()

            # Find numeric block (Mem) index
            try:
                mem_index = next(
                    i for i, t in enumerate(tokens) if re.fullmatch(r"\d+", t) and i > 3
                )
            except StopIteration:
                continue

            left = tokens[:mem_index]
            right = tokens[mem_index:]

            grp_no, tac, gtype = left[0], left[1], left[2]
            group_name = " ".join(left[3:])  # Preserve spaces in group name

            # Check for merged tail like 'ybothn15'
            if right:
                last_token = right[-1]
                tail_match = re.match(r"([yn])([a-zA-Z]+)([yn])(\d+)", last_token)
                if tail_match:
                    cdr, meas, dsp, length = tail_match.groups()
                    right = right[:-1] + [cdr, meas, dsp, length]

            # Adjust list size (Mem..Len = 8 tokens)
            if len(right) > 8:
                right = right[:8]
            elif len(right) < 8:
                right += [""] * (8 - len(right))

            row = [grp_no, tac, gtype, group_name] + right[:8]
            row += [""] * (len(columns) - len(row))
            records.append(row[: len(columns)])

    df = pd.DataFrame(records, columns=columns)

    

    return df


# ==============================
# UI wrapper (Option A) - minimal and non-invasive
# ==============================
def run_list_trunk_group(ip, password, custom_command=None):
    """
    Wrapper so UI can pass IP + password dynamically (Option A).
    Leaves ALL existing logic untouched.
    """
    global SAT_HOST, SAT_PASSWORD, SAT_USERNAME

    SAT_HOST = ip
    SAT_PASSWORD = password
    SAT_USERNAME = "dadmin"

    return run_avaya_command(custom_command)


# ==============================
# Main Execution
# ==============================
def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ✅ enforce the exact prefix used by the backend app.py glob pattern
    safe_prefix = "list_trunk-group"
    excel_file = os.path.join(REPORT_DIR, f"{safe_prefix}_{timestamp}.xlsx")

    try:
        # ✅ run command with new SSH logic
        output = run_avaya_command(COMMAND)
        df = parse_list_trunk_group(output)

        # --- Write to Excel with formatting ---
        with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="List_Trunk_Group", index=False)
            ws = writer.sheets["List_Trunk_Group"]

            # ✅ Style headers like in yesterday_peak.py
            from openpyxl.styles import Font, Alignment
            bold = Font(bold=True)
            for cell in ws[1]:
                cell.font = bold
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # ✅ Auto width for all columns
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
