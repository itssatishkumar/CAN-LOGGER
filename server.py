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

# 6 = 7th tab, 4 = 5th tab
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


def load_from_sheet():
    global clients
    clients = {}

    try:
        # Start reading from row 2, header row untouched
        rows = sheet.get_all_values()

        for row in rows[1:]:
            if len(row) < 4:
                continue

            device = row[0].strip()
            user_info = row[1].strip()
            login_time = row[2].strip()
            last_seen = row[3].strip()

            if not user_info:
                continue

            clients[user_info] = {
                "device": device,
                "login_time": login_time,
                "last_seen": last_seen
            }

    except Exception as e:
        print("Load error:", e)
        clients = {}


def save_to_sheet():
    try:
        # Read all rows, but do not touch row 1
        rows = sheet.get_all_values()

        # Map USER INFO from column B to sheet row number
        row_map = {}

        for idx, row in enumerate(rows[1:], start=2):
            if len(row) >= 2:
                user_info = row[1].strip()
                if user_info:
                    row_map[user_info] = idx

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


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.json or {}

    device = data.get("device", "unknown")
    name = data.get("name", device)
    event = data.get("event", "heartbeat")

    now = now_ist()

    # Same USER INFO = overwrite same row
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
