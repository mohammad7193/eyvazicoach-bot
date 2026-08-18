import os
import requests
import datetime
import pytz
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
         return "یک پست صبح بخیر پرانرژی. یادآوری نعمت‌هایی که خدا به ما داده و شکرگزاری بابت زندگی. **قانون بسیار مهم:** به هیچ وجه، تحت هیچ شرایطی کلماتی مثل پول، مالیات، بیمه، حسابداری یا کسب‌وکار در این پست استفاده نشود."
    elif hour < 12:
         return "یک پست تخصصی و کاربردی درباره مسائل و قوانین مالیاتی."
    elif hour < 15:
         return "آموزش کاربردی حسابداری برای مدیران."
    elif hour < 18:
         return "نکات کلیدی در مورد سامانه مودیان یا قوانین بیمه پرسنل."
    else:
         return "تکنیک‌های مدیریت هزینه‌های کسب‌وکار یا زندگی شخصی."

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
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            return response["photos"][0]["src"]["large"]
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

    # ۲. ارسال به بله (الگوی موفق شتاب‌افزا: ارسال مستقیم لینک URL عکس به جای بایت‌های multipart در صورت ناسازگاری سرور)
    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        
        bale_payload = {
            "chat_id": BALE_CHAT,
            "photo": image_url,  # ارسال لینک مستقیم تصویر به جای فایل باینری (مورد تایید مستندات و تست‌شده در شتاب‌افزا)
            "caption": bale_caption
        }
        
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
        res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
        print(f"Bale Status: {res_bale.status_code}")
        print(f"Bale Response Text: {res_bale.text}")
        
    except Exception as e:
        print(f"Bale Error: {e}")

if __name__ == "__main__":
    topic = get_current_topic()
    caption, query = generate_content(topic)
    
    image_url = get_pexels_image(query)
    if not image_url:
        image_url = "https://images.pexels.com/photos/3184291/pexels-photo-3184291.jpeg" # لینک فال‌بک مستقیم و امن پکسلز
        
    send_post(caption, image_url)
