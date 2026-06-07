from flask import Flask, request, jsonify
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import json
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# -------- CONFIG --------
SHEET_ID = "1nDkL93epR1RQfFvCrzAVeiu5a9TpaU2484sOaVkQAQw"

# 7th tab = index 6 because gspread starts from 0
WORKSHEET_INDEX = 6

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -------- GOOGLE SHEETS AUTH --------
creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SHEET_ID).get_worksheet(WORKSHEET_INDEX)

# -------- MEMORY --------
clients = {}


def now_ist():
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()


def ensure_header():
    header = [
        "DEVISE NAME",
        "USER INFO",
        "APP",
        "VERSION",
        "PLATFORM",
        "LOGIN",
        "LAST SEEN",
        "LAST EVENT"
    ]

    values = sheet.get_all_values()

    if not values:
        sheet.append_row(header)
    elif values[0] != header:
        sheet.update("A1:H1", [header])


def load_from_sheet():
    global clients
    clients = {}

    try:
        ensure_header()
        rows = sheet.get_all_records()

        for row in rows:
            device = row.get("DEVISE NAME", "")
            if not device:
                continue

            clients[device] = {
                "name": row.get("USER INFO", ""),
                "app": row.get("APP", ""),
                "version": row.get("VERSION", ""),
                "platform": row.get("PLATFORM", ""),
                "login_time": row.get("LOGIN", ""),
                "last_seen": row.get("LAST SEEN", ""),
                "last_event": row.get("LAST EVENT", "")
            }

    except Exception as e:
        print("Load error:", e)
        clients = {}


def save_to_sheet():
    try:
        ensure_header()

        rows = sheet.get_all_records()
        row_map = {
            row.get("DEVISE NAME", ""): idx + 2
            for idx, row in enumerate(rows)
        }

        for device, info in clients.items():
            row_data = [
                device,
                info.get("name", ""),
                info.get("app", ""),
                info.get("version", ""),
                info.get("platform", ""),
                info.get("login_time", ""),
                info.get("last_seen", ""),
                info.get("last_event", "")
            ]

            if device in row_map:
                row_no = row_map[device]
                sheet.update(f"A{row_no}:H{row_no}", [row_data])
            else:
                sheet.append_row(row_data)

    except Exception as e:
        print("Save error:", e)


# -------- LOAD EXISTING SHEET DATA --------
load_from_sheet()


# -------- ROUTES --------
@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.json or {}

    device = data.get("device", "unknown")
    name = data.get("name", device)
    app_name = data.get("app", "CAN Logger")
    version = data.get("version", "")
    platform_name = data.get("platform", "")
    event = data.get("event", "heartbeat")

    now = now_ist()

    if device not in clients or event == "opened":
        clients[device] = {
            "name": name,
            "app": app_name,
            "version": version,
            "platform": platform_name,
            "login_time": now,
            "last_seen": now,
            "last_event": event
        }
    else:
        clients[device]["name"] = name
        clients[device]["app"] = app_name
        clients[device]["version"] = version
        clients[device]["platform"] = platform_name
        clients[device]["last_seen"] = now
        clients[device]["last_event"] = event

    save_to_sheet()

    return jsonify({
        "ok": True,
        "device": device,
        "event": event,
        "time": now
    })


@app.route("/clients", methods=["GET"])
def get_clients():
    return jsonify(clients)


@app.route("/")
def home():
    return "Server running"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
