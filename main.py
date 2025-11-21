import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]


def send_message(chat_id: int, text: str):
    """שולח הודעה לטלגרם בחזרה לקבוצה."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})


def call_gpt(message: str) -> str:
    """קורא ל־OpenAI כדי לקבל תגובה של 'צלע שלישית'."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a gentle, humorous, non-judgmental third-wheel bot "
                    "inside a couple's Telegram group chat. "
                    "Your job is to lightly support their communication about intimacy, "
                    "desire, and emotions. "
                    "You respond only when it is likely to be helpful. "
                    "If the message does not require any intervention from you, "
                    "respond with exactly: NO_REPLY"
                ),
            },
            {"role": "user", "content": message},
        ],
    }
    r = requests.post(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


@app.route("/", methods=["GET", "POST"])
def webhook():
    """נקודת הכניסה שמקבלת עדכונים מטלגרם."""
    # בדיקת חיים פשוטה – Render / הדפדפן
    if request.method == "GET":
        return "OK", 200

    data = request.get_json(silent=True) or {}
    print("Incoming update:", data, flush=True)

    message = data.get("message")
    if not message:
        return "OK", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return "OK", 200

    try:
        reply = call_gpt(text)
        if reply != "NO_REPLY":
            send_message(chat_id, reply)
    except Exception as e:
        # לוג שגיאות
        print("Error:", e, flush=True)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
