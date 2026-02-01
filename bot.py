import os
from flask import Flask, request
import telebot
import google.generativeai as genai

# الإعدادات (تأكد من صحتها)
TOKEN = "8531055332:AAGAT8Q7UMlyAHjOif1IJwyrZGcEZYLhmW4"
GEMINI_KEY = "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"
CHANNEL_ID = "2904278551"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعداد Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT = "تقمص شخصية شاب مصري بائس وشيك. اكتب عبارة سوداء ساخرة (25-30 حرف) بقافية شعبية مصرية. أريد العبارة فقط."

# المسار الثابت للويب هوك
@app.route('/webhook', methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Forbidden", 403

@app.route('/')
def index():
    return "البوت شغال يا برنس ومستني الويب هوك!", 200

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "أهلاً يا برنس.. جاهز للنكد الشيك؟ ابعت أي حاجة وهرد عليك بقافية.")

@bot.message_handler(func=lambda message: True)
def handle_all(message):
    try:
        response = model.generate_content(PROMPT)
        bot.reply_to(message, response.text.strip())
    except:
        bot.reply_to(message, "الوسواس زاد والرد تاه..")

if __name__ == "__main__":
    # تفعيل الويب هوك أوتوماتيكياً على المسار الجديد
    bot.remove_webhook()
    bot.set_webhook(url="https://dicash.onrender.com/webhook")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
