import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

AUTHORIZED_TELEGRAM_ID = "6667327731"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", "10000"))
DB = "licenses.db"

app = Flask(__name__)

def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS licenses(
        code TEXT PRIMARY KEY,
        telegram_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        used INTEGER NOT NULL DEFAULT 0
    )""")
    con.commit()
    return con

def now():
    return datetime.now(timezone.utc)

def send_bot(chat_id, text):
    if not BOT_TOKEN:
        return
    import requests
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )

@app.get("/")
def home():
    return {"ok": True, "service": "@alexunc license server"}

@app.post("/telegram/start")
def telegram_start():
    data = request.get_json(silent=True) or {}
    telegram_id = str(data.get("telegram_id", "")).strip()

    if telegram_id != AUTHORIZED_TELEGRAM_ID:
        return jsonify(ok=False, error="unauthorized"), 403

    code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].upper()
    con = db()
    con.execute(
        "INSERT INTO licenses(code,telegram_id,created_at) VALUES(?,?,?)",
        (code, telegram_id, now().isoformat()),
    )
    con.commit()
    con.close()

    send_bot(
        telegram_id,
        f"@alexunc activation code: {code}\n"
        "Open the program and enter this code. Access lasts 24 hours from activation."
    )
    return {"ok": True, "code": code}

@app.post("/activate")
def activate():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()

    con = db()
    row = con.execute(
        "SELECT telegram_id,expires_at,used FROM licenses WHERE code=?",
        (code,),
    ).fetchone()

    if not row:
        con.close()
        return jsonify(status="denied")

    telegram_id, expires_at, used = row

    if expires_at:
        exp = datetime.fromisoformat(expires_at)
        if now() >= exp:
            con.close()
            return jsonify(status="expired")

    if used:
        con.close()
        return jsonify(status="denied")

    exp = now() + timedelta(days=1)
    con.execute(
        "UPDATE licenses SET used=1,expires_at=? WHERE code=?",
        (exp.isoformat(), code),
    )
    con.commit()
    con.close()

    return {
        "status": "ok",
        "telegram_id": telegram_id,
        "expires_at": exp.isoformat()
    }

if __name__ == "__main__":
    db().close()
    app.run(host="0.0.0.0", port=PORT)
