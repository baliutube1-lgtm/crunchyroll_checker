import os
import asyncio
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

# ✅ Load from Railway environment variables
BOT_TOKEN = os.getenv("8704844082:AAGJYybxhWMugb6oiL3Zg1L4K2xvtEd7cVI")
CHAT_ID = os.getenv("8677251975")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# ✅ Send message
async def send_telegram(text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            TELEGRAM_URL,
            json={"chat_id": CHAT_ID, "text": text}
        )

# ================= WEBHOOK =================
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message")

    if not message:
        return {"ok": True}

    chat_id = str(message.get("chat", {}).get("id"))
    text = message.get("text", "")

    if chat_id != CHAT_ID:
        return {"ok": True}

    if text == "/start":
        await send_telegram("✅ Bot is running on Railway!")

    elif text == "/check":
        await send_telegram("🚀 Processing started...")

        for i in range(1, 51):
            await asyncio.sleep(0.2)

            if i % 10 == 0:
                await send_telegram(f"📊 Progress: {i}/50")

        await send_telegram("✅ Done!")

    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "Bot running on Railway 🚀"}
