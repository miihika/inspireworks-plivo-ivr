"""Trigger a call through the local dashboard API without a browser."""
import argparse
import json
import re
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--to", help="Destination in international format; defaults to .env")
args = parser.parse_args()
try:
    with urlopen("http://127.0.0.1:5000/") as response:
        html = response.read().decode()
    token = re.search(r'data-token="([^"]+)"', html).group(1)
    payload = {"to": args.to} if args.to else {}
    request = Request("http://127.0.0.1:5000/api/call", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "X-Demo-Token": token}, method="POST")
    with urlopen(request) as response:
        print(response.read().decode())
except Exception as exc:
    print("Call could not be initiated. Check that app.py is running and .env is configured.")
    if hasattr(exc, "read"):
        print(exc.read().decode())
    raise SystemExit(1)
