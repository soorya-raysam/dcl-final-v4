#!/usr/bin/env python3
import re
import json

SAMPLE_OUTPUT = """
CTI   Version  Mnt   AE Services      Service       Msgs     Msgs
Link           Busy  Server           State         Sent     Rcvd
 1     7       no    aesnode06        established   53127    52185
 2     0       no    -                no            0        0
 3     0       no    -                no            0        0
 4     0       no    -                no            0        0
 5     0       no    -                no            0        0
 6     0       no    -                no            0        0
 7     12      no    p133-aes         established   3572     3559
 8     0       no    -                no            0        0
10     0       no    inpucsaes0001    established   15313    15241
11     0       no    incdszaes0001    established   15       15
12     0       no    inphlpaes0001    established   6691     6691
13     0       no    -                no            0        0
14     0       no    -                no            0        0
"""

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


if __name__ == "__main__":
    result = parse_cti_link(SAMPLE_OUTPUT)
    print(json.dumps(result, indent=2))
