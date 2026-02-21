import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
CHAT_HISTORY = {}  # {chat_id: [{"role": "user"/"assistant", "content": "..."}]}
MAX_TURNS = 8



def send_message(chat_id: int, text: str):
    """שולח הודעה לטלגרם בחזרה לקבוצה."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def call_gpt(chat_id: int) -> str:
    """קורא ל־OpenAI עם היסטוריה קצרה כדי לקבל תגובה פחות רובוטית."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}

    system_prompt = """You are Triia, a smart, grounded, humorous "third wheel" inside a couple's Telegram group.
You are NOT a therapist. No diagnosis. No clichés. No exaggerated positivity. No infantilizing tone.

Rules:
- Be specific to what they said. Avoid generic advice.
- Prefer one sharp reflection + one strong question.
- 1–4 short sentences max. Use spoken Hebrew if they write Hebrew.
- If you add no value: output exactly NO_REPLY.

Depth recipe:
Name the dynamic. Reflect both sides fairly. Ask one question that opens the next layer (need, desire, fear, boundary, meaning)."""

    history = CHAT_HISTORY.get(chat_id, [])[-MAX_TURNS:]
    messages = [{"role": "system", "content": system_prompt}] + history

    data = {
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": 220,
        "messages": messages,
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
        # Save user message to history
history = CHAT_HISTORY.get(chat_id, [])
history.append({"role": "user", "content": text})
CHAT_HISTORY[chat_id] = history[-MAX_TURNS:]

# Decide when to respond (reduce noise + cost)
lower = text.lower()
addressed = ("triia" in lower) or ("טריה" in text)
tension = any(k in text for k in ["פער", "תשוקה", "מיניות", "ריב", "כעס", "פגוע", "פגועה", "מתוסכל", "בגידה", "קנאה"])

user_count = sum(1 for m in CHAT_HISTORY.get(chat_id, []) if m["role"] == "user")

# Respond only when addressed, or tension exists, or every 5th user message
if not addressed and not tension and (user_count % 5 != 0):
    return "OK", 200


    try:
       reply = call_gpt(chat_id)
        if reply != "NO_REPLY":
            send_message(chat_id, reply)
            history = CHAT_HISTORY.get(chat_id, [])
history.append({"role": "assistant", "content": reply})
CHAT_HISTORY[chat_id] = history[-MAX_TURNS:]

    except Exception as e:
        # לוג שגיאות
        print("Error:", e, flush=True)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
