import telebot
import asyncio
from fastapi import FastAPI, Request

app = FastAPI()

# 🔑 PUT YOUR NEW TOKEN HERE (NOT OLD ONE)
TOKEN =  "8677251975:AAGuEGmCIvQLUKO4j4dM7wGYMAExldG7ftM"

bot = telebot.TeleBot(TOKEN)

# ================== ROOT ==================
@app.get("/")
async def root():
    return {"status": "Bot running"}

# ================== WEBHOOK ==================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        print(data)  # Debug log

        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]

            # Handle only text messages
            text = msg.get("text")
            if not text:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "Please send text only 😊"
                )
                return {"ok": True}

            text = text.strip().lower()

            # /start command
            if text == "/start":
                user = msg["from"]

                if user.get("username"):
                    name = f"@{user['username']}"
                else:
                    name = user.get("first_name", "there")

                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    f"Hello {name} 👋\n\nSend me: 5 + 3"
                )

            # Calculator
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
