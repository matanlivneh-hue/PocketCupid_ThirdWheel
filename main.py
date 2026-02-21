import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

# Simple in-memory history per chat (resets on redeploy / free-tier sleep)
CHAT_HISTORY = {}  # {chat_id: [{"role": "user"/"assistant", "content": "..."}]}
MAX_TURNS = 12  # keep last N turns total (user+assistant)


def send_message(chat_id: int, text: str):
    """Send a message back to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Keep it simple. If you later want Markdown, add: "parse_mode": "Markdown"
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)


def call_gpt(chat_id: int) -> str:
    """Call OpenAI with short history to get a better, less-robotic reply."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}

    system_prompt = """You are Triia, a smart, grounded, playful "third wheel" inside a couple's Telegram group.
Goal: make the conversation more alive: witty, emotionally intelligent, and game-like — without being a therapist.

Hard rules:
- Not a therapist. No diagnosis. No prescriptive advice like “you should”. No judging. No taking sides.
- No clichés. No “communication is important”. No generic pep talk.
- 1–4 short sentences only.
- Be specific to their words. Quote 2–6 words they used when helpful.
- If you truly add no value, output exactly NO_REPLY.

Style:
- Adult, sharp, warm. Light humor. A little cheeky, never childish.
- Innovative, playful, and concrete: prefer a tiny game / prompt over abstract reflections.
- Avoid “overly positive” tone. No forced validation. Be real and accurate.

Play deck (choose ONE per response, keep it short):
1) One-liner appreciation: each writes one concrete sentence of appreciation (no “you’re amazing”).
2) Curious switch: each guesses what the other needs right now, then confirm/adjust.
3) Flirty micro-dare: a tiny bold invitation that is safe and fun (PG-13, no explicit content).
4) Memory spark: a shared memory that makes them feel like a team.
5) Desire translation: “When you say X, do you mean closeness, novelty, safety, or being wanted?”
6) Two truths: each shares 2 true things: one easy, one vulnerable, one sentence each.

Few-shot examples (match the vibe):
User: "We keep missing each other lately."
Assistant: "Sounds like you’re both reaching, just at different times. Quick game: each write one concrete thing you miss about the other this week. One sentence each."

User: "Triia, our desire gap is killing the mood."
Assistant: "I hear frustration and longing underneath. Tiny experiment: each answer in one line — ‘I feel desired when…’ and ‘I shut down when…’"

User: "ok"
Assistant: NO_REPLY

Now respond to the next message in the same style."""

    history = CHAT_HISTORY.get(chat_id, [])[-MAX_TURNS:]
    messages = [{"role": "system", "content": system_prompt}] + history

    data = {
        "model": "gpt-4o-mini",
        "temperature": 0.9,
        "max_tokens": 180,
        "presence_penalty": 0.6,
        "frequency_penalty": 0.3,
        "messages": messages,
    }

    r = requests.post(url, headers=headers, json=data, timeout=25)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def should_respond(chat_id: int, text: str) -> bool:
    """Decide when Triia should speak (reduce noise + cost, increase relevance)."""
    lower = text.lower()

    # Direct addressing
    addressed = ("triia" in lower) or ("טריה" in text)

    # Tension / intimacy markers (Hebrew + some English)
    tension_markers = [
        "פער", "תשוקה", "מיניות", "ריב", "כעס", "פגוע", "פגועה", "מתוסכל", "מתוסכלת",
        "בגידה", "קנאה", "דחייה", "נעלבתי", "נפגעתי", "לא רוצה", "לא רצית", "אין לי חשק",
        "intimacy", "desire", "sex", "flirt", "jealous", "hurt", "angry"
    ]
    tension = any(k in text for k in tension_markers)

    # Respond every 5th user message to add lightweight steering
    history = CHAT_HISTORY.get(chat_id, [])
    user_count = sum(1 for m in history if m["role"] == "user")
    every_fifth = (user_count % 5 == 0)

    return addressed or tension or every_fifth


@app.route("/", methods=["GET", "POST"])
def webhook():
    """Entry point for Telegram updates."""
    if request.method == "GET":
        return "OK", 200

    data = request.get_json(silent=True) or {}
    print("Incoming update:", data, flush=True)

    message = data.get("message")
    if not message:
        return "OK", 200

    # Ignore messages sent by bots (prevents loops / weird behavior)
    sender = message.get("from", {}) or {}
    if sender.get("is_bot"):
        return "OK", 200

    chat = message.get("chat", {}) or {}
    chat_id = chat.get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return "OK", 200

    # Ignore Telegram commands
    if text.startswith("/"):
        return "OK", 200

    # Save user message to short history
    history = CHAT_HISTORY.get(chat_id, [])
    history.append({"role": "user", "content": text})
    CHAT_HISTORY[chat_id] = history[-MAX_TURNS:]

    # Decide if Triia should respond
    if not should_respond(chat_id, text):
        return "OK", 200

    try:
        reply = call_gpt(chat_id)

        if reply == "NO_REPLY":
            return "OK", 200

        send_message(chat_id, reply)

        # Save assistant reply to history
        history = CHAT_HISTORY.get(chat_id, [])
        history.append({"role": "assistant", "content": reply})
        CHAT_HISTORY[chat_id] = history[-MAX_TURNS:]

    except Exception as e:
        print("Error:", e, flush=True)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
