import os
import requests
import datetime
import pytz
import random
import google.generativeai as genai

# دریافت متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

# تنظیم مدل جمینای
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

def get_current_topic():
    iran_tz = pytz.timezone('Asia/Tehran')
    hour = datetime.datetime.now(iran_tz).hour

    if hour < 9:
         topics = [
             "Gratitude for the simple blessings in life.",
             "Starting the day with positive energy and a clear mind.",
             "Appreciating health, family, and a fresh morning.",
             "Finding peace in the early hours before the rush of the day begins."
         ]
         base_rule = " STRICT RULE: NEVER mention finance, taxes, insurance, accounting, or business."
         return random.choice(topics) + base_rule
         
    elif hour < 12:
         topics = [
             "Common mistakes businesses make with value-added tax (VAT).",
             "How proper tax planning saves companies from bankruptcy.",
             "Recent changes or essential rules in corporate tax laws.",
             "The importance of transparency in tax declarations for startups."
         ]
         return random.choice(topics)
         
    elif hour < 15:
         topics = [
             "Why cash flow management is more important than profit margins.",
             "How to correctly read a basic balance sheet for non-accountants.",
             "The difference between bookkeeping and strategic accounting.",
             "Signs that a business urgently needs a professional accountant."
         ]
         return random.choice(topics)
         
    elif hour < 18:
         topics = [
             "Step-by-step logic of the Samaneh Moadiyan (Taxpayer System).",
             "Consequences of ignoring employee insurance laws for employers.",
             "How to legally optimize personnel insurance costs.",
             "Deadline reminders and tips for submitting Moadiyan invoices."
         ]
         return random.choice(topics)
         
    else:
         topics = [
             "The 50/30/20 rule for personal budget management.",
             "Identifying and cutting hidden operational costs in a small business.",
             "How inflation impacts purchasing power and how to hedge against it.",
             "The psychological aspect of unnecessary spending and how to stop it."
         ]
         return random.choice(topics)

def generate_content(topic):
    prompt = f"""
    You are an expert content creator for "Eyvazi Coach", a financial, tax, and accounting consulting firm.
    Write a Persian (Farsi) microblog post based strictly on this topic: {topic}
    
    CRITICAL RULES:
    1. NEVER use markdown asterisks (*) for bolding. If you need to emphasize a word, use HTML tags like <b>word</b>.
    2. Format: A catchy hook title (with an emoji), 3 to 4 lines of practical explanation, and a very short conclusion.
    3. Length: Maximum 70 to 100 words. Keep paragraphs short and scannable.
    4. At the very end of the text, on a new line, add exactly: @eyvazicoach
    
    After the Persian text, output exactly three dashes "---" on a new line.
    Then, provide a 1 to 3 words English search query for the Pexels API to find a high-quality, realistic image matching the post context.
    """
    
    response = model.generate_content(prompt)
    content = response.text.split("---")
    
    caption = content[0].strip()
    image_query = content[1].strip() if len(content) > 1 else "business lifestyle"
    
    return caption, image_query

def get_pexels_image(query):
    try:
        # دریافت 15 عکس برای جلوگیری از تکراری شدن تصاویر
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            # انتخاب تصادفی یک عکس از لیست نتایج
            random_photo = random.choice(response["photos"])
            return random_photo["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return None

def send_post(caption, image_url):
    # ۱. ارسال به تلگرام
    try:
        img_response = requests.get(image_url, timeout=15)
        img_data = img_response.content
        
        tg_payload = {
            "chat_id": TELEGRAM_CHAT,
            "caption": caption,
            "parse_mode": "HTML"
        }
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
        print(f"Telegram Status: {res_tg.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

    # ۲. ارسال به بله (الگوی موفق: ارسال مستقیم لینک عکس)
    try:
        # پاک‌سازی تگ‌های HTML برای جلوگیری از به‌هم‌ریختگی در بله
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        
        bale_payload = {
            "chat_id": BALE_CHAT,
            "photo": image_url,
            "caption": bale_caption
        }
        
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
        res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
        
        print("--- BALE DEBUG REPORT ---")
        print(f"Bale Status Code: {res_bale.status_code}")
        print(f"Bale Raw Response: {res_bale.text}")
        print("-------------------------")
        
    except Exception as e:
        print(f"Bale Connection Exception: {e}")

if __name__ == "__main__":
    topic = get_current_topic()
    caption, query = generate_content(topic)
    
    image_url = get_pexels_image(query)
    if not image_url:
        # لینک امن جایگزین در صورت قطعی پکسلز
        image_url = "https://images.pexels.com/photos/3184291/pexels-photo-3184291.jpeg"
        
    send_post(caption, image_url)
