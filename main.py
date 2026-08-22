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
    history = history[-50:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item in history:
            f.write(item + "\n")

def get_latest_news(history):
    rss_urls = ["https://www.tasnimnews.com/fa/rss/feed/0/8/0/"]
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            title = entry.title
            if title not in history:
                return title, entry.link
    return None, None

def determine_post_type():
    iran_tz = pytz.timezone('Asia/Tehran')
    hour = datetime.datetime.now(iran_tz).hour
    
    # ساعت‌های آموزشی: 10 و 16 / ساعت‌های خبری: 13 و 19
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
            print("خبر جدیدی یافت نشد. خروج از برنامه برای جلوگیری از ارسال محتوای فیک.")
            exit(0)
            
        topic_context = f"خبر موثق اقتصادی/مالیاتی: {news_title}"
        save_history(news_title)
    else:
        # موضوعات فوق‌تخصصی، ریز و کاربردی (بدون کلی‌گویی)
        micro_topics = [
            "نحوه ابطال یا اصلاح صورتحساب الکترونیکی در سامانه مودیان در صورت درج قیمت اشتباه",
            "حدمجاز فروش ماده ۶ قانون پایانه‌های فروشگاهی و نحوه افزایش آن",
            "مهلت ۲۱ روزه خریدار برای تایید یا رد صورتحساب در کارپوشه و عواقب عدم اقدام",
            "تفاوت قرارداد کار معین و قرارداد کار موقت و نحوه محاسبه سنوات پرسنل",
            "جرایم ماده ۱۶۹ مکرر مالیات‌های مستقیم در صورت عدم ارسال معاملات فصلی",
            "روش اصولی تفکیک حساب‌های تجاری از شخصی برای جلوگیری از تشخیص درآمد غیرواقعی",
            "نحوه محاسبه استهلاک دارایی‌های ثابت طبق جدول ماده ۱۴۹ قانون مالیات‌ها",
            "مسئولیت تضامنی مدیران شرکت در پرداخت بدهی‌های مالیاتی و تامین اجتماعی",
            "آیا به عیدی و پاداش پایان سال پرسنل حق بیمه تامین اجتماعی تعلق می‌گیرد؟",
            "هزینه‌های قابل قبول مالیاتی طبق ماده ۱۴۷ و ۱۴۸ که ممیز نمی‌تواند رد کند"
        ]
        
        available_topics = [t for t in micro_topics if t not in history]
        if not available_topics:
            available_topics = micro_topics
            
        selected_topic = random.choice(available_topics)
        topic_context = f"نکته فنی و اجرایی: {selected_topic}"
        save_history(selected_topic)

    prompt = f"""
    You are a senior tax and accounting consultant writing a direct, high-value post for business managers on Telegram/Bale.
    Topic: "{topic_context}"
    
    STRICT CONTENT GUIDELINES:
    1. AVOID GENERALIZATIONS: Be highly specific, factual, and straight to the point. Do not use generic filler words, fluff, or state the obvious.
    2. NEWS ACCURACY (CRITICAL): If the topic is a news update, you MUST stick exactly to the provided facts in the topic. DO NOT alter, invent, change numbers, or hallucinate any information.
    3. NO PROMOTIONS: ABSOLUTELY NO COURSE SELLING or MARKETING. DO NOT use promotional phrases like "در این دوره", "ثبت نام کنید", etc.
    4. Structure: 
       - Line 1: Strong technical/news title with 1 relevant emoji (e.g. 📌, ⚖️, or 📰).
       - Paragraph 1 (3-4 lines): The exact legal rule, procedural step, or news summary without fluff.
       - Paragraph 2 (1 short line): The key takeaway or actionable advice.
       - Last line: @eyvazicoach
    5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
    6. Length: 60 to 90 words maximum.
    
    After the text, output exactly "---" on a new line, then provide a 1-3 words English query for Pexels.
    IMAGE QUERY RULES: Only inanimate office objects (e.g. "fountain pen document", "vintage calculator", "financial ledger", "office stamps"). NO humans, NO abstract concepts.
    """
    
    response = model.generate_content(prompt)
    content = response.text.split("---")
    
    caption = content[0].strip()
    image_query = content[1].strip() if len(content) > 1 else "business papers"
    
    return caption, image_query

def get_pexels_image(query):
    try:
        safe_query = query + " still life office"
        url = f"https://api.pexels.com/v1/search?query={safe_query}&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            random_photo = random.choice(response["photos"])
            return random_photo["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return "https://images.pexels.com/photos/53621/calculator-calculation-insurance-finance-53621.jpeg"

def send_post(caption, image_url):
    # ۱. تلگرام
    try:
        img_response = requests.get(image_url, timeout=15)
        img_data = img_response.content
        
        tg_payload = {"chat_id": TELEGRAM_CHAT, "caption": caption, "parse_mode": "HTML"}
        tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
        print(f"Telegram Status: {res_tg.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

    # ۲. بله
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
