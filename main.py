import os
import telebot
import asyncio
from fastapi import FastAPI, Request

app = FastAPI()

# 🔑 PUT YOUR TOKEN HERE (or use Railway variable BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN") or "8677251975:AAGuEGmCIvQLUKO4j4dM7wGYMAExldG7ftM"

bot = telebot.TeleBot(TOKEN)

# ================= ROOT =================
@app.get("/")
async def root():
    return {"status": "Bot is running 🚀"}

# ================= WEBHOOK =================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()

        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip().lower()

            # /start command
            if text == "/start":
                user = msg["from"]

                name = user.get("username")
                if name:
                    name = f"@{name}"
                else:
                    name = user.get("first_name", "there")

                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    f"Hello {name} 👋\n\nSend me: 5 + 3"
                )

            # calculator
            elif any(op in text for op in ["+", "-", "*", "/"]):
                try:
                    result = eval(text)
                    await asyncio.to_thread(
                        bot.send_message,
                        chat_id,
                        f"Result: {result}"
                    )
                except:
                    await asyncio.to_thread(
                        bot.send_message,
                        chat_id,
                        "❌ Invalid expression"
                    )

            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "Send a calculation like:\n5 + 3"
                )

    except Exception as e:
        print("Error:", e)

    return {"ok": True}
