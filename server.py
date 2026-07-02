from flask import Flask, Response, jsonify, request
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
import base64
import os
import json

import gspread
from google.oauth2.service_account import Credentials


app = Flask(__name__)

# -------- CONFIG --------
SHEET_ID = "1nDkL93epR1RQfFvCrzAVeiu5a9TpaU2484sOaVkQAQw"

# gspread indexes are zero-based: 7 = 8th tab / Sheet8.
WORKSHEET_INDEX = 7
CLIENT_ROWS_START = 34
SNAPSHOT_PANEL_RANGE = "A1:R32"
SNAPSHOT_FORMULA_CELL = "A1"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -------- GOOGLE SHEETS AUTH --------
creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SHEET_ID).get_worksheet(WORKSHEET_INDEX)

# -------- MEMORY --------
# Key = USER INFO
clients = {}
snapshots = {}


def now_ist():
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y %H:%M:%S")


def _public_base_url():
    return request.host_url.rstrip("/")


def _snapshot_url(user_info):
    return f"{_public_base_url()}/snapshot/{quote(user_info, safe='')}.jpg"


def load_from_sheet():
    global clients
    clients = {}

    try:
        rows = sheet.get_all_values()

        for row in rows[CLIENT_ROWS_START - 1:]:
            if len(row) < 4:
                continue

            device = row[0].strip()
            user_info = row[1].strip()
            login_time = row[2].strip()
            last_seen = row[3].strip()
            last_snapshot = row[4].strip() if len(row) > 4 else ""

            if not user_info:
                continue

            clients[user_info] = {
                "device": device,
                "login_time": login_time,
                "last_seen": last_seen,
                "last_snapshot": last_snapshot,
            }

    except Exception as e:
        print("Load error:", e)
        clients = {}


def save_to_sheet():
    try:
        rows = sheet.get_all_values()

        row_map = {}
        for idx, row in enumerate(rows[CLIENT_ROWS_START - 1:], start=CLIENT_ROWS_START):
            if len(row) >= 2:
                user_info = row[1].strip()
                if user_info:
                    row_map[user_info] = idx

        for user_info, info in clients.items():
            row_data = [
                info.get("device", ""),
                user_info,
                info.get("login_time", ""),
                info.get("last_seen", ""),
                info.get("last_snapshot", ""),
            ]

            if user_info in row_map:
                row_no = row_map[user_info]
                sheet.update(f"A{row_no}:E{row_no}", [row_data])
            else:
                sheet.append_row(row_data)

    except Exception as e:
        print("Save error:", e)


def update_snapshot_panel(user_info):
    try:
        image_url = f"{_snapshot_url(user_info)}?t={quote(now_ist(), safe='')}"
        escaped_url = image_url.replace('"', '""')
        sheet.update(SNAPSHOT_FORMULA_CELL, [[f'=IMAGE("{escaped_url}", 1)']], value_input_option="USER_ENTERED")
        sheet.update("A32", [[image_url]])
        sheet.update("A33:E33", [["Device", "User Info", "Login Time", "Last Seen", "Last Snapshot"]])
    except Exception as e:
        print("Snapshot panel update error:", e)


# -------- LOAD EXISTING SHEET DATA --------
load_from_sheet()


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.json or {}

    device = data.get("device", "unknown")
    name = data.get("name", device)
    event = data.get("event", "heartbeat")

    now = now_ist()

    if name not in clients or event == "opened":
        clients[name] = {
            "device": device,
            "login_time": now,
            "last_seen": now,
            "last_snapshot": clients.get(name, {}).get("last_snapshot", ""),
        }
    else:
        clients[name]["device"] = device
        clients[name]["last_seen"] = now

    save_to_sheet()

    return jsonify({
        "ok": True,
        "device": device,
        "name": name,
        "event": event,
        "time": now,
    })


@app.route("/snapshot", methods=["POST"])
def receive_snapshot():
    data = request.json or {}

    device = data.get("device", "unknown")
    name = data.get("name", device)
    encoded = data.get("image_jpg_base64", "")
    if not encoded:
        return jsonify({"ok": False, "error": "missing image_jpg_base64"}), 400

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        return jsonify({"ok": False, "error": "invalid image_jpg_base64"}), 400

    now = now_ist()
    snapshots[name] = {
        "device": device,
        "updated_at": now,
        "image": image_bytes,
        "width": data.get("image_width", ""),
        "height": data.get("image_height", ""),
    }

    if name not in clients:
        clients[name] = {
            "device": device,
            "login_time": now,
            "last_seen": now,
            "last_snapshot": now,
        }
    else:
        clients[name]["device"] = device
        clients[name]["last_seen"] = now
        clients[name]["last_snapshot"] = now

    update_snapshot_panel(name)
    save_to_sheet()

    return jsonify({
        "ok": True,
        "device": device,
        "name": name,
        "snapshot_url": _snapshot_url(name),
        "time": now,
    })


@app.route("/snapshot/<path:user_info>.jpg", methods=["GET"])
def get_snapshot(user_info):
    snapshot = snapshots.get(user_info)
    if not snapshot:
        return Response("No snapshot yet", status=404)

    response = Response(snapshot["image"], mimetype="image/jpeg")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/clients", methods=["GET"])
def get_clients():
    return jsonify(clients)


@app.route("/", methods=["GET"])
def home():
    return "Server running"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
