import os
import telebot
import asyncio
import requests
from fastapi import FastAPI, Request

app = FastAPI()

# 🔑 Put your token here OR use environment variable
TOKEN = "8677251975:AAGuEGmCIvQLUKO4j4dM7wGYMAExldG7ftM"

bot = telebot.TeleBot(TOKEN)

# ========================== CRUNCHYROLL CHECK ==========================
def check_crunchyroll(email: str, password: str) -> str:
    try:
        login_resp = requests.post(
            'https://beta-api.crunchyroll.com/auth/v1/token',
            data={
                'username': email,
                'password': password,
                'grant_type': 'password',
                'scope': 'offline_access'
            },
            headers={'User-Agent': 'Crunchyroll/3.0.0 Android'},
            auth=('cr_android', '1cf35dc5-b286-4551-8835-d4b1b4258445')
        )

        if login_resp.status_code != 200:
            return "❌ Invalid email or password"

        token = login_resp.json().get('access_token')

        profile_resp = requests.get(
            'https://beta-api.crunchyroll.com/accounts/v1/me',
            headers={'Authorization': f'Bearer {token}'}
        )

        external_id = profile_resp.json().get('external_id')

        sub_resp = requests.get(
            f'https://beta-api.crunchyroll.com/subs/v1/subscriptions/{external_id}/benefits',
            headers={'Authorization': f'Bearer {token}'}
        )

        if sub_resp.status_code == 200 and sub_resp.json().get('items'):
            benefit = sub_resp.json()['items'][0].get('benefit')
            if benefit == 'cr_premium':
                return "✅ Premium Active"
            else:
                return "⚠️ Free / Trial account"
        else:
            return "🔴 No active subscription"

    except Exception as e:
        return f"❌ Error: {str(e)}"


# ========================== ROUTES ==========================

@app.get("/")
async def root():
    return {"status": "Bot running"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()

        if "message" in data:
            msg = data["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()

            # /start command
            if text.lower() in ["/start", "/help"]:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "👋 Send your details like:\n\nemail:password"
                )
                return {"ok": True}

            # check format
            if ":" in text:
                email, password = [x.strip() for x in text.split(":", 1)]

                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "🔄 Checking..."
                )

                result = check_crunchyroll(email, password)

                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    f"📊 Result:\n{result}"
                )
            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "❌ Send in format:\nemail:password"
                )

    except Exception as e:
        print("Error:", e)

    return {"ok": True}
