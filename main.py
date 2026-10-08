import os
import requests
import datetime
import pytz
import random
import re
import google.generativeai as genai

# متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
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

def save_history(snippet):
    history = load_history()
    history.append(snippet)
    history = history[-100:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item in history:
            f.write(item + "\n")

def clean_telegram_text(raw_html):
    text = re.sub(r'<br\s*/?>', '\n', raw_html)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()

def scrape_telegram_channel(channel_username):
    url = f"https://t.me/s/{channel_username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
            
        html = resp.text
        message_blocks = re.findall(r'<div class="tgme_widget_message_wrap[^"]*">([\s\S]*?)</div>\s*</div>\s*</div>', html)
        
        extracted_posts = []
        for block in message_blocks[-7:]:
            img_match = re.search(r'background-image:url\(\'([^\']+)\'\)', block)
            image_url = img_match.group(1) if img_match else None
            
            text_match = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>', block)
            if not text_match:
                continue
                
            clean_text = clean_telegram_text(text_match.group(1))
            if len(clean_text) > 40:
                extracted_posts.append({
                    "text": clean_text,
                    "image": image_url
                })
        return extracted_posts
    except Exception as e:
        print(f"Error scraping @{channel_username}: {e}")
        return []

def is_post_valuable(raw_text):
    banned_words = ['ثبت نام دوره', 'ظرفیت محدود', 'کد تخفیف', 'مشاوره رایگان تماس', 'آگهی استخدام', 'رزومه بفرستید']
    for bad in banned_words:
        if bad in raw_text:
            return False
            
    try:
        prompt = f"""
        تو سردبیر تخصصی یک کانال مرجع در حوزه حسابداری، مالیات و حقوق کسب‌وکار هستی.
        متن زیر از یک کانال تخصصی تلگرام کپی شده است:
        ---
        {raw_text[:400]}
        ---
        شرایط تایید:
        1. متن نباید صرفاً یک تبلیغ، پکیج آموزشی، تبلیغ نرم‌افزار، یا آگهی استخدام باشد.
        2. باید حاوی بخشنامه رسمی، مهلت قانونی، آموزش کاربردی، نرخ جدید، یا خبر مهم مالیاتی/بیمه‌ای باشد.
        
        آیا این پست ارزش بازنشر برای فعالان اقتصادی دارد؟
        فقط بنویس: YES یا NO
        """
        response = model.generate_content(prompt)
        return "YES" in response.text.upper()
    except Exception:
        return True

def get_best_telegram_post(history):
    target_channels = ["taxpress", "taxinformation", "rahbarhesab", "Econ_Fouri"]
    random.shuffle(target_channels)
    
    for ch in target_channels:
        posts = scrape_telegram_channel(ch)
        for post in reversed(posts):
            snippet = post["text"][:60].strip()
            if snippet in history:
                continue
                
            if is_post_valuable(post["text"]):
                save_history(snippet)
                return post["text"], post["image"]
                
    return None, None

def generate_channel_content():
    history = load_history()
    raw_text, image_url = get_best_telegram_post(history)
    
    if not raw_text:
        return None, None

    prompt = f"""
    You are an expert Iranian financial, tax, and labor consultant drafting an official post for Telegram/Bale in Persian.
    Raw content extracted from authoritative tax channels:
    ---
    {raw_text}
    ---

    STRICT EDITORIAL GUIDELINES:
    1. REWRITE & POLISH: Transform this raw information into a fluent, cohesive, and professional post. Remove all external channel mentions, admin contacts, and promo links.
    2. DIRECT & FACTUAL: Keep all accurate dates, rates, and circular references. Do not invent any numbers.
    3. NO PREACHING: Deliver the news or practical rule fluidly without artificial labels like "پیامد:" or "راهکار:".
    4. LENGTH: 60 to 80 words maximum. Concise, neat, and high-impact.
    5. STRUCTURE:
       - Line 1: Clear and engaging title with 1 relevant emoji (e.g., 📌, ⚖️, 🚨).
       - Body: 1 or 2 well-structured paragraphs.
       - Last line: @eyvazicoach
    6. FORMATTING: Use <b>bold</b> for key words. NEVER use markdown asterisks (*).
    """
    response = model.generate_content(prompt)
    caption = response.text.strip()
    return caption, image_url

def send_post(caption, image_url=None, schedule_date=None):
    tg_payload = {"chat_id": TELEGRAM_CHAT, "parse_mode": "HTML"}
    bale_payload = {"chat_id": BALE_CHAT}
    
    if schedule_date:
        tg_payload["schedule_date"] = schedule_date
        bale_payload["schedule_date"] = schedule_date

    if image_url:
        try:
            img_response = requests.get(image_url, timeout=15)
            img_data = img_response.content
            tg_payload["caption"] = caption
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
            print(f"Telegram Photo Status: {res_tg.status_code}")
        except Exception as e:
            print(f"Telegram Photo Error: {e}")
            
        try:
            bale_caption = caption.replace('<b>', '').replace('</b>', '')
            bale_payload["caption"] = bale_caption
            bale_payload["photo"] = image_url
            bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
            res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
            print(f"Bale Photo Status: {res_bale.status_code}")
        except Exception as e:
            print(f"Bale Photo Error: {e}")
    else:
        try:
            tg_payload["text"] = caption
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            res_tg = requests.post(tg_url, data=tg_payload)
            print(f"Telegram Text Status: {res_tg.status_code}")
        except Exception as e:
            print(f"Telegram Text Error: {e}")
            
        try:
            bale_caption = caption.replace('<b>', '').replace('</b>', '')
            bale_payload["text"] = bale_caption
            bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
            res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
            print(f"Bale Text Status: {res_bale.status_code}")
        except Exception as e:
            print(f"Bale Text Error: {e}")

def get_next_target():
    iran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.datetime.now(iran_tz)
    
    schedule_hours = [10, 13, 16, 19]
    for target_hour in schedule_hours:
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now < target_time:
            return target_time
            
    return now.replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)

if __name__ == "__main__":
    target_time = get_next_target()
    schedule_timestamp = int(target_time.timestamp())
    
    iran_tz = pytz.timezone('Asia/Tehran')
    print(f"زمان اجرا: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')}")
    print(f"بررسی کانال‌های مرجع برای زمان‌بندی در ساعت {target_time.strftime('%H:%M:%S')}...")
    
    caption, image_url = generate_channel_content()
    
    if not caption:
        print("هیچ خبر معتبر جدیدی در کانال‌های مرجع یافت نشد.")
        exit(0)
        
    if image_url:
        print(f"ارسال با تصویر اصلی کانال مرجع: {image_url}")
        send_post(caption, image_url=image_url, schedule_date=schedule_timestamp)
    else:
        print("پست فاقد تصویر بود، ارسال به صورت متنی انجام می‌شود.")
        send_post(caption, image_url=None, schedule_date=schedule_timestamp)
