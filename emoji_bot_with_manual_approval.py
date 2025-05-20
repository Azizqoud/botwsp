
import os
import subprocess
import random
import requests
import json
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from gtts import gTTS
import cloudinary
import cloudinary.uploader
from elevenlabs import ElevenLabs

# تحميل المتغيرات من ملف config.txt
with open("config.txt", "r", encoding="utf-8") as f:
    lines = f.read().splitlines()
    ELEVEN_API_KEY = lines[0].split("=")[1].strip()
    CLOUD_NAME = lines[1].split("=")[1].strip()
    API_KEY = lines[2].split("=")[1].strip()
    API_SECRET = lines[3].split("=")[1].strip()

os.environ["ELEVEN_API_KEY"] = ELEVEN_API_KEY
cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)
client = ElevenLabs(api_key=ELEVEN_API_KEY)

RESPONSES_FILE = "responses.json"
USERS_FILE = "subscribers.json"
REQUESTS_FILE = "pending_requests.json"

# تحميل البيانات
if os.path.exists(RESPONSES_FILE):
    with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
        RESPONSES = json.load(f)
else:
    RESPONSES = {}

if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        SUBSCRIBERS = json.load(f)
else:
    SUBSCRIBERS = []

if os.path.exists(REQUESTS_FILE):
    with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
        PENDING = json.load(f)
else:
    PENDING = []

pending_users = {}

app = Flask(__name__)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    from_number = request.values.get("From", "")
    msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()

    # طلب اشتراك
    if msg.lower() == "اشتراك":
        if from_number in SUBSCRIBERS:
            resp.message("✅ أنت مشترك بالفعل.")
        elif from_number in PENDING:
            resp.message("⌛ طلبك قيد المراجعة. يرجى الانتظار.")
        else:
            PENDING.append(from_number)
            with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                json.dump(PENDING, f, ensure_ascii=False, indent=2)
            resp.message("📩 تم إرسال طلب الاشتراك. سيتم مراجعته من المشرف.")
        return str(resp)

    # إلغاء الاشتراك
    if msg.lower() == "ايقاف":
        if from_number in SUBSCRIBERS:
            SUBSCRIBERS.remove(from_number)
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(SUBSCRIBERS, f, ensure_ascii=False, indent=2)
            resp.message("🛑 تم إلغاء اشتراكك.")
        else:
            resp.message("❌ أنت غير مشترك.")
        return str(resp)

    # فقط المشتركين يرد عليهم
    if from_number not in SUBSCRIBERS:
        resp.message("🔒 الخدمة مخصصة للمشتركين فقط. أرسل 'اشتراك' لطلب الاشتراك.")
        return str(resp)

    # تحديث الإيموجي أو الرد
    if from_number in pending_users:
        emoji = pending_users.pop(from_number)
        RESPONSES[emoji] = msg
        with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
            json.dump(RESPONSES, f, ensure_ascii=False, indent=2)
        resp.message(f"✅ تم حفظ الرد الجديد للإيموجي {emoji}")
        return str(resp)

    if len(set(msg)) == 1 and msg[0] in RESPONSES and len(msg) == 3:
        emoji = msg[0]
        pending_users[from_number] = emoji
        resp.message(f"🛠️ تريد تحديث الرد للإيموجي {emoji}. أرسل لي الرد الجديد.")
        return str(resp)

    if msg not in RESPONSES and len(msg) <= 2:
        pending_users[from_number] = msg
        resp.message(f"📝 لا يوجد رد لهذا الإيموجي: {msg}\nاكتب لي الرد الآن لحفظه.")
        return str(resp)

    reply_text = RESPONSES.get(msg, msg)
    try:
        tts = gTTS(reply_text, lang="ar")
        filename = f"audio_{random.randint(1000,9999)}.mp3"
        tts.save(filename)

        upload_result = cloudinary.uploader.upload(filename, resource_type="video")
        audio_url = upload_result["secure_url"]

        message = resp.message(f"🗣️ {reply_text}")
        message.media(audio_url)
        return str(resp)

    except Exception as e:
        print("❌ خطأ:", e)
        resp.message("حدث خطأ أثناء تحويل النص إلى صوت.")
        return str(resp)

# نقطة نهاية لقبول/رفض المستخدمين (للمشرف)
@app.route("/admin/approve", methods=["POST"])
def approve_user():
    data = request.json
    number = data.get("number")
    if number in PENDING:
        PENDING.remove(number)
        SUBSCRIBERS.append(number)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(SUBSCRIBERS, f, ensure_ascii=False, indent=2)
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(PENDING, f, ensure_ascii=False, indent=2)
        return {"status": "approved"}, 200
    return {"error": "not found"}, 404

@app.route("/admin/reject", methods=["POST"])
def reject_user():
    data = request.json
    number = data.get("number")
    if number in PENDING:
        PENDING.remove(number)
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(PENDING, f, ensure_ascii=False, indent=2)
        return {"status": "rejected"}, 200
    return {"error": "not found"}, 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
