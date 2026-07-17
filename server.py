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

# 6 = seventh worksheet tab
WORKSHEET_INDEX = 6

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


# -------- GOOGLE SHEETS AUTH --------

creds_json = json.loads(
    os.environ["GOOGLE_SERVICE_ACCOUNT"]
)

creds = Credentials.from_service_account_info(
    creds_json,
    scopes=SCOPES
)

client = gspread.authorize(creds)

sheet = client.open_by_key(
    SHEET_ID
).get_worksheet(WORKSHEET_INDEX)


# -------- MEMORY --------
# Key = USER INFO

clients = {}


def now_ist():
    return datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%d-%m-%Y %H:%M:%S")


def load_from_sheet():
    global clients

    clients = {}

    try:
        # Read the worksheet while leaving row 1 as the header.
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

    except Exception as exc:
        print("Load error:", exc)
        clients = {}


def save_to_sheet():
    try:
        # Read all rows, but do not modify the header row.
        rows = sheet.get_all_values()

        # Map USER INFO in column B to its worksheet row number.
        row_map = {}

        for row_number, row in enumerate(
            rows[1:],
            start=2
        ):
            if len(row) < 2:
                continue

            user_info = row[1].strip()

            if user_info:
                row_map[user_info] = row_number

        for user_info, info in clients.items():
            row_data = [
                info.get("device", ""),
                user_info,
                info.get("login_time", ""),
                info.get("last_seen", "")
            ]

            if user_info in row_map:
                # Existing user: update only columns A–D.
                row_number = row_map[user_info]

                sheet.update(
                    f"A{row_number}:D{row_number}",
                    [row_data],
                    value_input_option="USER_ENTERED"
                )

            else:
                # New user: force append into the A–D table.
                # This prevents Google Sheets from selecting F–I.
                sheet.append_row(
                    row_data,
                    value_input_option="USER_ENTERED",
                    table_range="A:D"
                )

    except Exception as exc:
        print("Save error:", exc)


# -------- LOAD EXISTING SHEET DATA --------

load_from_sheet()


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    data = request.get_json(silent=True) or {}

    device = str(
        data.get("device", "unknown")
    ).strip()

    name = str(
        data.get("name", device)
    ).strip()

    event = str(
        data.get("event", "heartbeat")
    ).strip()

    if not device:
        device = "unknown"

    if not name:
        name = device

    current_time = now_ist()

    # Same USER INFO updates the same stored client.
    if name not in clients or event == "opened":
        clients[name] = {
            "device": device,
            "login_time": current_time,
            "last_seen": current_time
        }

    else:
        clients[name]["device"] = device
        clients[name]["last_seen"] = current_time

    save_to_sheet()

    return jsonify({
        "ok": True,
        "device": device,
        "name": name,
        "event": event,
        "time": current_time
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
