import os
import requests
import datetime
import pytz
import random
import feedparser
import re
import hashlib
import google.generativeai as genai

# دریافت متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"

def get_text_hash(text):
    # ایجاد یک اثر انگشت یکتا از متن برای جلوگیری قطعی از تکرار
    clean = re.sub(r'\s+', '', text[:120])
    return hashlib.md5(clean.encode('utf-8')).hexdigest()

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_history(text_hash):
    history = load_history()
    if text_hash not in history:
        history.append(text_hash)
    history = history[-300:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item in history:
            f.write(item + "\n")

def clean_raw_text(raw_html):
    text = re.sub(r'<br\s*/?>', '\n', raw_html)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    # حذف شماره‌های تلفن و عبارات تبلیغاتی رایج از انتهای متن
    text = re.sub(r'09\d{9}', '', text)
    text = re.sub(r'۰۹[۰-۹]{9}', '', text)
    return text.strip()

def is_clean_and_relevant(text):
    if len(text) < 50:
        return False
        
    # لیست سیاه جامع برای مسدودسازی تبلیغات دوره‌ها، اساتید و فروش در سطح کد
    ad_keywords = [
        'دوره', 'کارگاه', 'وبینار', 'سمینار', 'ثبت نام', 'ثبت‌نام', 'شهریه', 
        'تخفیف', 'ظرفیت', 'استاد', 'مدرس', 'پکیج', 'فروش', 'خرید', 'مشاوره', 
        'تماس بگیرید', 'شماره تماس', 'لینک زیر', 'کلیک کنید', 'استخدام', 'رزومه',
        'همکاری', 'کانال ما', 'پیج', 'اینستاگرام', 'واتساپ', 'تلگرام', 'هدیه',
        'رایگان', 'قرعه کشی', 'قرعه‌کشی', 'اسپانسر', 'تبلیغات', 'معرفی کتاب',
        'نرم افزار', 'نرم‌افزار', 'دمو', 'جشنواره', 'کد معرف', 'آکادمی', 'موسسه'
    ]
    for bad in ad_keywords:
        if bad in text:
            return False
            
    # کلمات الزامی تخصصی
    valid_keywords = [
        'مالیات', 'ارزش افزوده', 'مودی', 'مؤدی', 'مودیان', 'سامانه مودیان', 
        'اظهارنامه', 'بخشنامه', 'تبصره', 'ماده', 'معافیت', 'پایانه فروشگاهی', 
        'جرایم', 'جریمه', 'صورتحساب', 'الکترونیکی', 'کارفرما', 'کارگر', 
        'حقوق', 'دستمزد', 'بیمه', 'تامین اجتماعی', 'دیوان عدالت', 'دادنامه'
    ]
    return any(k in text for k in valid_keywords)

def get_intamedia_candidates(history):
    """دریافت اخبار مستقیم از سازمان امور مالیاتی (همراه با عکس رسمی)"""
    candidates = []
    rss_urls = [
        "https://www.intamedia.ir/rss",
        "https://www.intamedia.ir/news/rss"
    ]
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.title.strip()
                summary = clean_raw_text(getattr(entry, 'summary', title))
                full_text = f"{title}\n{summary}"
                
                t_hash = get_text_hash(full_text)
                if t_hash in history:
                    continue
                    
                if is_clean_and_relevant(full_text):
                    img_url = None
                    if hasattr(entry, 'enclosures') and entry.enclosures:
                        raw_img = entry.enclosures[0].get('href', '')
                        if raw_img.startswith('http'):
                            img_url = raw_img
                    candidates.append({
                        "text": full_text,
                        "image": img_url,
                        "hash": t_hash,
                        "source": "intamedia.ir"
                    })
        except Exception as e:
            print(f"Intamedia RSS error: {e}")
    return candidates

def scrape_telegram_candidates(history):
    """دریافت متن اطلاعیه‌ها از کانال‌های مرجع (بدون عکس جهت جلوگیری از بنرهای تبلیغاتی)"""
    target_channels = ["taxpress", "taxinformation", "rahbarhesab", "Econ_Fouri"]
    random.shuffle(target_channels)
    candidates = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    for ch in target_channels:
        try:
            resp = requests.get(f"https://t.me/s/{ch}", headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
                
            message_blocks = re.findall(r'<div class="tgme_widget_message_wrap[^"]*">([\s\S]*?)</div>\s*</div>\s*</div>', resp.text)
            for block in reversed(message_blocks[-8:]):
                text_match = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>', block)
                if not text_match:
                    continue
                    
                clean_text = clean_raw_text(text_match.group(1))
                t_hash = get_text_hash(clean_text)
                
                if t_hash in history:
                    continue
                    
                if is_clean_and_relevant(clean_text):
                    candidates.append({
                        "text": clean_text,
                        "image": None,  # عدم استخراج عکس از تلگرام برای حذف ۱۰۰٪ پوسترهای تبلیغاتی
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
            
    return candidates

def generate_verified_post():
    history = load_history()
    
    # جمع‌آوری کاندیداها (اولویت اول: سایت سازمان مالیاتی، اولویت دوم: کانال‌ها)
    candidates = get_intamedia_candidates(history) + scrape_telegram_candidates(history)
    
    if not candidates:
        return None, None

    # بررسی حداکثر ۳ کاندیدا در هر نوبت (حفظ سهمیه API و رد کردن تبلیغات مخفی)
    for item in candidates[:3]:
        save_history(item["hash"])  # ثبت فوری در تاریخچه تا دیگر هرگز بررسی نشود
        
        prompt = f"""
        You are the strict Chief Editor for "@eyvazicoach", an official Iranian tax, accounting, and business legal channel.
        Analyze the following raw text:
        ---
        {item["text"]}
        ---

        STEP 1 - ANTI-PROMOTION & QUALITY GATEKEEPER (CRITICAL):
        Reject this text immediately and output ONLY the exact word "REJECT_AD" if ANY of the following is true:
        - It promotes or mentions a course, webinar, workshop, seminar, book, software, or consultation.
        - It mentions another teacher, instructor, person's name, academy, or institute.
        - It is an incomplete sentence referring to "the image above", "the clip below", or "the attached file".
        - It is trivial gossip or has no practical tax/insurance/business legal value.

        STEP 2 - REWRITE & POLISH (Only if it passes Step 1):
        Rewrite the pure legal/tax/economic news or circular into a dignified, fluent Persian post:
        1. Keep exact numbers, dates, and legal references accurate. Do not invent facts.
        2. Write naturally in 55 to 75 words. No preaching, no labels like "پیامد:" or "نکته:".
        3. Structure:
           - Line 1: 1 relevant emoji (📌, ⚖️, or 📋) + Bold Title.
           - Body: 1 or 2 clean, cohesive paragraphs.
           - Last line: @eyvazicoach
        4. Formatting: Use <b>bold</b> for emphasis. NEVER use asterisks (*).
        """
        try:
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            if "REJECT_AD" in result_text or len(result_text) < 40:
                print(f"پست استخراج‌شده از {item['source']} توسط سردبیر هوش مصنوعی به دلیل تبلیغاتی/نامعتبر بودن رد شد.")
                continue
                
            print(f"پست معتبر و خالص از {item['source']} تایید و آماده شد.")
            return result_text, item["image"]
            
        except Exception as e:
            print(f"Gemini API Error: {e}")
            break
            
    return None, None

def send_post(caption, image_url=None, schedule_date=None):
    tg_payload = {"chat_id": TELEGRAM_CHAT, "parse_mode": "HTML"}
    bale_payload = {"chat_id": BALE_CHAT}
    
    if schedule_date:
        tg_payload["schedule_date"] = schedule_date
        bale_payload["schedule_date"] = schedule_date

    if image_url and image_url.startswith('http'):
        img_sent = False
        try:
            img_response = requests.get(image_url, timeout=15)
            if img_response.status_code == 200:
                tg_payload["caption"] = caption
                tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_response.content, "image/jpeg")})
                print(f"Telegram Photo Status: {res_tg.status_code}")
                img_sent = (res_tg.status_code == 200)
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

        if not img_sent:
            send_text_only(caption, schedule_date)
    else:
        send_text_only(caption, schedule_date)

def send_text_only(caption, schedule_date=None):
    tg_payload = {"chat_id": TELEGRAM_CHAT, "text": caption, "parse_mode": "HTML"}
    bale_payload = {"chat_id": BALE_CHAT, "text": caption.replace('<b>', '').replace('</b>', '')}
    
    if schedule_date:
        tg_payload["schedule_date"] = schedule_date
        bale_payload["schedule_date"] = schedule_date
        
    try:
        res_tg = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=tg_payload, timeout=15)
        print(f"Telegram Text Status: {res_tg.status_code}")
    except Exception as e:
        print(f"Telegram Text Error: {e}")
        
    try:
        res_bale = requests.post(f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage", data=bale_payload, timeout=15)
        print(f"Bale Text Status: {res_bale.status_code}")
    except Exception as e:
        print(f"Bale Text Error: {e}")

def get_next_target():
    iran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.datetime.now(iran_tz)
    
    for target_hour in [10, 13, 16, 19]:
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now < target_time:
            return target_time
            
    return now.replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)

if __name__ == "__main__":
    target_time = get_next_target()
    schedule_timestamp = int(target_time.timestamp())
    
    iran_tz = pytz.timezone('Asia/Tehran')
    print(f"زمان اجرا: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')} | هدف زمان‌بندی: {target_time.strftime('%H:%M:%S')}")
    
    caption, image_url = generate_verified_post()
    
    if not caption:
        print("هیچ خبر غیرتبلیغاتی و جدیدی یافت نشد. خروج.")
        exit(0)
        
    send_post(caption, image_url=image_url, schedule_date=schedule_timestamp)
