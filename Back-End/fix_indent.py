import re

with open("app/api/routes/valuation.py", "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "fetch_treasury_risk_free_rate_sync()" in line:
        start_idx = i
    if "return telemetry" in line and start_idx != -1 and end_idx == -1:
        end_idx = i

if start_idx != -1 and end_idx != -1:
    for i in range(start_idx, end_idx + 1):
        if lines[i].strip():
            lines[i] = "    " + lines[i]

with open("app/api/routes/valuation.py", "w") as f:
    f.writelines(lines)
