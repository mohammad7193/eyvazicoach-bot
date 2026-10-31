import os
import requests
import datetime
import pytz
import random
import feedparser
import re
import hashlib
import io
import base64
import google.generativeai as genai

# متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"

# تنوع‌بخش‌های چیدمان سبک Editorial Flat Lay برای جلوگیری از تکراری شدن تصاویر
SURFACES = [
    "deep dark walnut wood office desk with subtle natural grain",
    "matte charcoal slate stone table with subtle mineral textures",
    "minimalist dark polished industrial concrete desk",
    "luxurious black marble desk with ultra-subtle gold and white veining",
    "executive smoked oak executive wooden table"
]

OBJECT_SETS = [
    "official governmental embossed folders, luxury gold-trimmed fountain pen, reading glasses, clean white ceramic espresso cup",
    "classic leather-bound legal case dossier, brass paperweights, elegant mechanical pencil, metallic paperclips",
    "contemporary sleek tablet showing formal analytical charts, opened heavy paper document folder, graphite stylus",
    "traditional wax seal stamp, premium cotton archive papers with official header stamps, classic magnifying glass",
    "clean modern desktop calculator, organized legal invoice stacks, minimalist matte black pen tray"
]

LIGHTING_MOODS = [
    "soft natural morning window side-lighting with delicate architectural shadows",
    "moody warm overhead brass desk lamp illumination creating rich contrast and depth",
    "diffused cinematic daylight casting soft, elegant shadows across the paper textures",
    "crisp high-end editorial studio lighting emphasizing paper embossing and desk grain"
]

def get_text_hash(text):
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
    text = re.sub(r'09\d{9}', '', text)
    text = re.sub(r'۰۹[۰-۹]{9}', '', text)
    return text.strip()

def is_clean_and_relevant(text):
    if len(text) < 50:
        return False
        
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
            
    valid_keywords = [
        'مالیات', 'ارزش افزوده', 'مودی', 'مؤدی', 'مودیان', 'سامانه مودیان', 
        'اظهارنامه', 'بخشنامه', 'تبصره', 'ماده', 'معافیت', 'پایانه فروشگاهی', 
        'جرایم', 'جریمه', 'صورتحساب', 'الکترونیکی', 'کارفرما', 'کارگر', 
        'حقوق', 'دستمزد', 'بیمه', 'تامین اجتماعی', 'دیوان عدالت', 'دادنامه'
    ]
    return any(k in text for k in valid_keywords)

def get_intamedia_candidates(history):
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
                    candidates.append({
                        "text": full_text,
                        "hash": t_hash,
                        "source": "intamedia.ir"
                    })
        except Exception as e:
            print(f"Intamedia RSS error: {e}")
    return candidates

def scrape_telegram_candidates(history):
    target_channels = ["taxpress", "taxinformation", "rahbarhesab", "Econ_Fouri"]
    random.shuffle(target_channels)
    candidates = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
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
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
    return candidates

def build_editorial_prompt(headline_persian):
    """ساخت پرامپت استوری به سبک Editorial Flat Lay با المان‌های متغیر و فضای منفی"""
    surface = random.choice(SURFACES)
    items = random.choice(OBJECT_SETS)
    light = random.choice(LIGHTING_MOODS)
    
    prompt = f"""Award-winning editorial flat lay top-down overhead photography for a prestigious financial journal. 
Vertical story framing (aspect ratio 9:16).
Background: High-end luxurious {surface}.
Composition and Layout: 
- Exactly the UPPER 50% of the frame is meticulously styled with authentic high-end items: {items}. Crisp paper texture with fine Iranian tax bureau seals and formal document headers.
- Exactly the LOWER 50% of the frame is completely clean, flat, empty NEGATIVE SPACE showing only the pure textured {surface}, perfectly clear for stickers.
Lighting and Atmosphere: {light}. Realistic depth of field, 8k resolution, cinematic tactile textures.
Negative Constraints: Absolutely NO human figures, NO faces, NO banknotes, NO coins, NO link stickers, NO UI elements, NO cartoon or 3D render aesthetics.
CRITICAL INSTRUCTION FOR TEXT: A pristine cream-colored official letterhead paper is placed at the top center. It clearly and accurately features the Persian headline rendered in elegant Iranian typography: "{headline_persian}". Persian script must be beautifully aligned, connected correctly, and perfectly legible --ar 9:16"""
    
    return prompt.strip()

def generate_story_image(prompt_text):
    """تولید تصویر استوری با مدل Imagen 3 بر اساس پرامپت اختصاصی"""
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GEMINI_API_KEY}"
        payload = {
            "instances": [{"prompt": prompt_text}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "9:16",
                "outputOptions": {"mimeType": "image/jpeg"}
            }
        }
        res = requests.post(api_url, json=payload, timeout=40)
        if res.status_code == 200:
            img_b64 = res.json()["predictions"][0]["bytesBase64Encoded"]
            return base64.b64decode(img_b64)
        else:
            print(f"Imagen API Error ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"Image generation error: {e}")
        return None

def generate_verified_package():
    history = load_history()
    candidates = get_intamedia_candidates(history) + scrape_telegram_candidates(history)
    
    if not candidates:
        return None, None, None

    for item in candidates[:3]:
        save_history(item["hash"])
        
        prompt = f"""
        نقش:
        تو طراح تخصصی استوری اینستاگرام و کپی‌رایتر مالیاتی-مدیریتی برای برند «EyvaziCoach» هستی.
        وظیفه تو تبدیل متن خبر/بخشنامه زیر به کپشن رسمی و خنثی است:
        ---
        {item["text"]}
        ---

        شرط بازبینی (مهم):
        اگر این متن هرگونه تبلیغ دوره، کارگاه، وبینار، نرم‌افزار، یا نام مدرس دیگری است، بلافاصله فقط بنویس: REJECT_AD

        دستورالعمل نگارش کپشن (Caption):
        - لحن کاملاً کوتاه، خنثی، رسمی و فاقد اضافه‌گویی
        - استخراج دقیق شماره بخشنامه، تاریخ‌های انقضا/مهلت و شروط کلیدی در قالب Bullet Points (•)
        - خط اول: تیتر صریح و بولد
        - خط آخر: 🌐 @EyvaziCoach
        - برای بولد کردن فقط از تگ <b>استفاده کن</b> و اصلاً ستاره (*) نگذار.

        بعد از نگارش کپشن، در یک خط جداگانه بنویس:
        ---HEADLINE---
        و در خط بعد فقط یک تیتر کوتاه و موجز فارسی (حداکثر ۵ تا ۶ کلمه) بنویس که باید روی سربرگ پوستر قرار گیرد.
        """
        try:
            response = text_model.generate_content(prompt)
            result = response.text.strip()
            
            if "REJECT_AD" in result or len(result) < 40:
                print(f"پست از {item['source']} به دلیل تبلیغاتی بودن رد شد.")
                continue
                
            parts = result.split("---HEADLINE---")
            caption = parts[0].strip()
            headline = parts[1].strip() if len(parts) > 1 else "اطلاعیه رسمی مالیاتی"
            
            # تولید پرامپت اختصاصی بر اساس سبک ژورنالیستی Editorial Flat Lay
            image_prompt = build_editorial_prompt(headline)
            print(f"Generated Editorial Prompt:\n{image_prompt}")
            
            image_bytes = generate_story_image(image_prompt)
            return caption, image_bytes, image_prompt
            
        except Exception as e:
            print(f"Content generation error: {e}")
            break
            
    return None, None, None

def send_to_channel_and_admin(caption, image_bytes=None, prompt_used=None, schedule_date=None):
    # ۱. ارسال پوستر استوری و کپشن به کانال اصلی (یا چت خصوصی در صورت تنظیم ID ادمین)
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto" if image_bytes else f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "parse_mode": "HTML"
    }
    if schedule_date:
        payload["schedule_date"] = schedule_date

    try:
        if image_bytes:
            payload["caption"] = caption
            files = {"photo": ("story_editorial.jpg", io.BytesIO(image_bytes), "image/jpeg")}
            res = requests.post(tg_url, data=payload, files=files, timeout=25)
        else:
            payload["text"] = caption
            res = requests.post(tg_url, data=payload, timeout=15)
        print(f"Telegram Post Status: {res.status_code}")
    except Exception as e:
        print(f"Telegram Error: {e}")

    # ۲. ارسال متن رسمی به بله
    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        requests.post(f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage", data={"chat_id": BALE_CHAT, "text": bale_caption}, timeout=15)
    except Exception as e:
        print(f"Bale Error: {e}")

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
    print(f"اجرا در ساعت: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')} | زمان انتشار: {target_time.strftime('%H:%M:%S')}")
    
    caption, image_bytes, prompt_used = generate_verified_package()
    if not caption:
        print("محتوای تاییدشده‌ای یافت نشد.")
        exit(0)
        
    send_to_channel_and_admin(caption, image_bytes=image_bytes, prompt_used=prompt_used, schedule_date=schedule_timestamp)
