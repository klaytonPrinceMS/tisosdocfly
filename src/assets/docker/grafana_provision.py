#!/usr/bin/env python3
"""
Grafana Dashboard Provisioning - Skyrover Modular

Provisions dashboards into Grafana via the HTTP API using basic auth
(which is the reliable method in Grafana 13+).

Provisão de dashboards no Grafana via API HTTP usando basic auth
(método confiável no Grafana 13+).

Usage:
    python grafana_provision.py [--dry-run]

Requirements:
    - Grafana running on http://localhost:3000
    - credentials master/master
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen, HTTPError

# Grafana connection settings
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
GRAFANA_USER = os.environ.get("GRAFANA_USER", "master")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD", "master")
DASHBOARDS_DIR = Path(__file__).parent / "config" / "grafana-dashboards"
FOLDER_TITLE = "Skyrover"


def _request(method: str, path: str, data=None, tries: int = 1):
    """Perform an HTTP request to Grafana with basic auth."""
    url = f"{GRAFANA_URL}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")

    import base64
    token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    for attempt in range(tries):
        try:
            with urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 401 and attempt < tries - 1:
                time.sleep(2)
                continue
            return e.code, {}
        except Exception as e:
            return 0, {"error": str(e)}
    return 0, {}


def ensure_folder() -> str:
    """Ensure the target folder exists and return its UID."""
    # Search for existing folder
    status, data = _request("GET", f"/api/search?type=dash-folder&query={FOLDER_TITLE}")
    if status == 200:
        for item in data:
            if item.get("title") == FOLDER_TITLE:
                return item["uid"]

    # Create folder
    status, data = _request("POST", "/api/folders", {"title": FOLDER_TITLE, "uid": "skyrover-folder"})
    if status in (200, 400) and data.get("uid"):
        return data["uid"]

    # If product returned an error but folder exists (bad request may still create)
    status, data = _request("GET", "/api/folders")
    for folder in (data or []):
        if folder.get("title") == FOLDER_TITLE:
            return folder["uid"]
    return ""


def provision_dashboard(filepath: Path, folder_uid: str):
    """Upload a single dashboard JSON."""
    dashboard = json.loads(filepath.read_text(encoding="utf-8"))
    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "folderUid": folder_uid,
        "message": "Provisioned by Skyrover Modular"
    }
    status, data = _request("POST", "/api/dashboards/db", payload)
    return status, data


def main():
    parser = argparse.ArgumentParser(description="Provision Grafana dashboards")
    parser.add_argument("--dry-run", action="store_true", help="List dashboards without uploading")
    args = parser.parse_args()

    print("=" * 50)
    print("Provisioning Grafana Dashboards - Skyrover Modular")
    print("=" * 50)
    print(f"Grafana: {GRAFANA_URL}")
    print(f"User:    {GRAFANA_USER}")
    print(f"Folders: {DASHBOARDS_DIR}")

    # Verify connectivity
    status, health = _request("GET", "/api/health")
    if status != 200:
        print(f"ERROR: Cannot reach Grafana at {GRAFANA_URL} (status={status})")
        print("Make sure the Docker stack is running: cd assets/docker && ./start.sh")
        sys.exit(1)
    print(f"Grafana OK (version {health.get('version', '?')})")

    # Ensure folder
    folder_uid = ensure_folder()
    if not folder_uid:
        print("WARNING: Could not create/get folder. Using default (General).")
        folder_uid = None
    else:
        print(f"Folder OK: '{FOLDER_TITLE}' (uid={folder_uid})")

    # Get dashboard files
    files = sorted(DASHBOARDS_DIR.glob("*.json"))
    if not files:
        print(f"No dashboards found in {DASHBOARDS_DIR}")
        sys.exit(0)

    print(f"Found {len(files)} dashboard(s):")
    for f in files:
        print(f"  - {f.name}")

    if args.dry_run:
        print("\nDry-run: no changes made.")
        return

    # Upload dashboards
    success = 0
    for f in files:
        status, data = provision_dashboard(f, folder_uid)
        if status in (200, 201):
            title = data.get("title", f.stem)
            uid = data.get("uid", "")
            print(f"  [OK]   {title} (uid={uid})")
            success += 1
        else:
            print(f"  [FAIL] {f.name}: status={status}")

    print(f"\nDone: {success}/{len(files)} dashboards provisioned.")
    if success < len(files):
        sys.exit(1)


if __name__ == "__main__":
    main()