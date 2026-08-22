import os
import requests
import datetime
import pytz
import random
import feedparser
import google.generativeai as genai

# متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()]

def save_history(title):
    history = load_history()
    history.append(title)
    # نگهداری فقط ۵۰ عنوان آخر برای جلوگیری از سنگین شدن فایل
    history = history[-50:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item in history:
            f.write(item + "\n")

def get_latest_news(history):
    # RSS اخبار اقتصادی تسنیم (میتوانی لینک سایت‌های مالیاتی دیگر را هم اینجا اضافه کنی)
    rss_urls = ["https://www.tasnimnews.com/fa/rss/feed/0/8/0/"]
    
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]: # بررسی 10 خبر اول
            title = entry.title
            if title not in history:
                return title, entry.link
    return None, None

def determine_post_type():
    iran_tz = pytz.timezone('Asia/Tehran')
    hour = datetime.datetime.now(iran_tz).hour
    
    # ساعت 10 و 16 پست آموزشی / ساعت 13 و 19 پست خبری
    if hour in [9, 10, 11, 15, 16, 17]:
        return "edu"
    else:
        return "news"

def generate_content():
    history = load_history()
    post_type = determine_post_type()
    
    if post_type == "news":
        news_title, news_link = get_latest_news(history)
        if not news_title:
            print("خبر جدیدی یافت نشد. پایان عملیات برای جلوگیری از تولید خبر فیک.")
            exit(0)
            
        topic_context = f"خبر اقتصادی/مالیاتی جدید: {news_title}"
        save_history(news_title)
    else:
        topics = [
            "آموزش کاربردی سامانه مودیان",
            "نکات کلیدی بیمه پرسنل برای کارفرمایان",
            "اشتباهات رایج در اظهارنامه مالیاتی",
            "مدیریت هزینه‌های سربار در کسب‌وکار",
            "اهمیت شفافیت مالی و حسابداری اصولی"
        ]
        # فیلتر کردن موضوعاتی که اخیراً استفاده شده‌اند
        available_topics = [t for t in topics if t not in history]
        if not available_topics:
            available_topics = topics # ریست کردن در صورت اتمام
            
        selected_topic = random.choice(available_topics)
        topic_context = f"آموزش تخصصی: {selected_topic}"
        save_history(selected_topic)

    prompt = f"""
    You are an expert content creator for "Eyvazi Coach", a financial and tax consulting firm.
    Write a Persian (Farsi) microblog post based strictly on this topic: "{topic_context}"
    
    CRITICAL RULES:
    1. NEVER use markdown asterisks (*) for bolding. Use HTML tags like <b>word</b>.
    2. Format: Catchy hook title (with emoji), 3 to 4 lines of explanation/news summary, and a short conclusion.
    3. Length: Maximum 70 to 100 words.
    4. At the end, add: @eyvazicoach
    
    After the Persian text, output exactly three dashes "---" on a new line.
    
    IMAGE SEARCH STRICT RULE:
    Provide a 1 to 3 words English search query for the Pexels API.
    CRITICAL: The image MUST ONLY feature inanimate objects like an empty office desk, calculator, paperwork, coffee mug, or financial charts. 
    NEVER use words related to humans, people, love, or morning routines to avoid inappropriate images.
    """
    
    response = model.generate_content(prompt)
    content = response.text.split("---")
    
    caption = content[0].strip()
    image_query = content[1].strip() if len(content) > 1 else "calculator desk"
    
    return caption, image_query

def get_pexels_image(query):
    try:
        # اضافه کردن کلمات کلیدی ایمن به کوئری برای اطمینان مضاعف
        safe_query = query + " office object"
        url = f"https://api.pexels.com/v1/search?query={safe_query}&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            random_photo = random.choice(response["photos"])
            return random_photo["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return "https://images.pexels.com/photos/53621/calculator-calculation-insurance-finance-53621.jpeg" # تصویر فال‌بک امن (ماشین‌حساب)

def send_post(caption, image_url):
    # ۱. ارسال به تلگرام
    try:
        img_response = requests.get(image_url, timeout=15)
        img_data = img_response.content
        
        tg_payload = {"chat_id": TELEGRAM_CHAT, "caption": caption, "parse_mode": "HTML"}
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
        print(f"Telegram Status: {res_tg.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

    # ۲. ارسال به بله (الگوی قطعی با لینک مستقیم و بدون تگ HTML)
    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        bale_payload = {"chat_id": BALE_CHAT, "photo": image_url, "caption": bale_caption}
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
        res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
        print(f"Bale Status: {res_bale.status_code}")
    except Exception as e:
        print(f"Bale Error: {e}")

if __name__ == "__main__":
    caption, query = generate_content()
    image_url = get_pexels_image(query)
    send_post(caption, image_url)
