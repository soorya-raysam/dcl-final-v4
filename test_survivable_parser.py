#!/usr/bin/env python3
import re
import json

SAMPLE_OUTPUT = """
SURVIVABLE PROCESSORS

Record Name/              Type        Reg Act   Translations       Net
Number  IP Address                               Updated           Rgn
1   BHUBANESWAR-LSPLSP    LSP          y   n    11:30 11/30/2025   24
    10.52.32.10

2   ESS-CHD-ESS-SYNC35    ESS          y   y    11:30 11/30/2025    8
    10.107.64.132

3   INPUCSESS00001        ESS          y   y    11:30 11/30/2025    7
    10.106.60.23

4   KOL-ST-ESS-SN-37      ESS          n   n                       37
    10.33.23.39
    No V6 Entry
"""

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


if __name__ == "__main__":
    parsed = parse_survivable_processor_output(SAMPLE_OUTPUT)

    print(json.dumps({
        "rows": len(parsed),
        "data": parsed
    }, indent=2))
