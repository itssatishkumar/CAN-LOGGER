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

# 7th tab = index 6
WORKSHEET_INDEX = 6

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -------- GOOGLE SHEETS AUTH --------
creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
client = gspread.authorize(creds)

sheet = client.open_by_key(SHEET_ID).get_worksheet(WORKSHEET_INDEX)

# -------- MEMORY --------
# Key = USER INFO
clients = {}


def now_ist():
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y %H:%M:%S")


def ensure_header():
    header = [
        "DEVICE NAME",
        "USER INFO",
        "LOGIN",
        "LAST SEEN"
    ]

    values = sheet.get_all_values()

    if not values:
        sheet.append_row(header)
    else:
        sheet.update("A1:D1", [header])


def load_from_sheet():
    global clients
    clients = {}

    try:
        ensure_header()
        rows = sheet.get_all_records()

        for row in rows:
            user_info = row.get("USER INFO", "")
            if not user_info:
                continue

            clients[user_info] = {
                "device": row.get("DEVICE NAME", ""),
                "login_time": row.get("LOGIN", ""),
                "last_seen": row.get("LAST SEEN", "")
            }

    except Exception as e:
        print("Load error:", e)
        clients = {}


def save_to_sheet():
    try:
        ensure_header()

        rows = sheet.get_all_records()

        # Find row by USER INFO, not DEVICE NAME
        row_map = {
            row.get("USER INFO", ""): idx + 2
            for idx, row in enumerate(rows)
            if row.get("USER INFO", "")
        }

        for user_info, info in clients.items():
            row_data = [
                info.get("device", ""),
                user_info,
                info.get("login_time", ""),
                info.get("last_seen", "")
            ]

            if user_info in row_map:
                row_no = row_map[user_info]
                sheet.update(f"A{row_no}:D{row_no}", [row_data])
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
    event = data.get("event", "heartbeat")

    now = now_ist()

    # Same USER INFO will overwrite same row
    if name not in clients or event == "opened":
        clients[name] = {
            "device": device,
            "login_time": now,
            "last_seen": now
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
        "time": now
    })


@app.route("/clients", methods=["GET"])
def get_clients():
    return jsonify(clients)


@app.route("/", methods=["GET"])
def home():
    return "Server running"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
