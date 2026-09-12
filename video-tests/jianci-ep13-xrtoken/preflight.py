import json, os, urllib.request, urllib.error
from pathlib import Path
key = os.environ.get("XRTOKEN", "").strip()
out = Path("output/jianci-ep13-xrtoken")
out.mkdir(parents=True, exist_ok=True)
report = {"secret_present": bool(key), "paid_requests": 0, "hosts": []}
if key:
    for host in ["https://api.xrtoken.ai", "https://api.xrtoken.net"]:
        row = {"host": host}
        try:
            req = urllib.request.Request(host + "/v1/videos/generations?limit=1", headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as res:
                data = json.load(res)
                row["http_status"] = res.status
                row["authenticated"] = True
        except urllib.error.HTTPError as exc:
            row["http_status"] = exc.code
            row["authenticated"] = False
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        report["hosts"].append(row)
        if row.get("authenticated"):
            report["base_url"] = host
            break
(out / "preflight.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
if "base_url" not in report:
    raise SystemExit(2)
