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

# دریافت متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")  # آیدی کانال عمومی
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")     # آیدی عددی چت خصوصی ادمین
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"

# تنوع‌بخش‌های چیدمان سبک Editorial Flat Lay برای جلوگیری از تکراری شدن استوری‌ها
SURFACES = [
    "deep dark walnut wood office desk with subtle natural grain",
    "matte charcoal slate stone table with subtle mineral textures",
    "minimalist dark polished industrial concrete desk",
    "luxurious black marble desk with ultra-subtle gold and white veining",
    "executive smoked oak wooden table"
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
        
    # فیلتر اخبار سال‌های گذشته
    old_years = ['۱۴۰۲', '1402', '۱۴۰۳', '1403']
    for old_y in old_years:
        if old_y in text and '۱۴۰۵' not in text and '1405' not in text:
            return False

    # لیست سیاه تبلیغات، دوره‌ها و همایش‌ها
    ad_keywords = [
        'دوره', 'کارگاه', 'وبینار', 'سمینار', 'ثبت نام', 'ثبت‌نام', 'شهریه', 
        'تخفیف', 'ظرفیت', 'استاد', 'مدرس', 'پکیج', 'فروش', 'خرید', 'مشاوره', 
        'تماس بگیرید', 'شماره تماس', 'لینک زیر', 'کلیک کنید', 'استخدام', 'رزومه',
        'همکاری', 'کانال ما', 'پیج', 'اینستاگرام', 'واتساپ', 'تلگرام', 'هدیه',
        'رایگان', 'قرعه کشی', 'قرعه‌کشی', 'اسپانسر', 'تبلیغات', 'معرفی کتاب',
        'نرم افزار', 'نرم‌افزار', 'دمو', 'جشنواره', 'کد معرف', 'آکادمی', 'موسسه',
        'پروژه', 'تحقق', 'درآمد مالیاتی', 'استاندار', 'شهردار', 'فرماندار', 'افتتاح'
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
    """رصد مستقیم سازمان امور مالیاتی کشور (intamedia.ir)"""
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
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": "intamedia.ir"
                    })
        except Exception as e:
            print(f"Intamedia RSS error: {e}")
    return candidates

def scrape_telegram_candidates(history):
    """رصد کانال‌های تخصصی مرجع"""
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
                        "image_url": None,
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
    return candidates

def build_editorial_prompt(headline_persian):
    """ساخت پرامپت استوری به سبک Editorial Flat Lay فقط با تیتر اصلی روی برگه"""
    surface = random.choice(SURFACES)
    items = random.choice(OBJECT_SETS)
    light = random.choice(LIGHTING_MOODS)
    
    prompt = f"""Award-winning editorial flat lay top-down overhead photography for a prestigious financial journal. 
Vertical story framing (aspect ratio 9:16).
Background: High-end luxurious {surface}.
Composition and Layout: 
- Exactly the UPPER 50% of the frame is meticulously styled with authentic high-end items: {items}, surrounding a central official cream-colored letterhead paper with an embossed Iranian administrative emblem.
- Exactly the LOWER 50% of the frame is completely clean, flat, empty NEGATIVE SPACE showing only the pure textured {surface}, perfectly clear for stickers.
Lighting and Atmosphere: {light}. Realistic depth of field, 8k resolution, cinematic tactile textures.
Negative Constraints: Absolutely NO human figures, NO faces, NO banknotes, NO coins, NO link stickers, NO UI elements, NO body paragraphs or summary text, NO cartoon or 3D render aesthetics.
CRITICAL INSTRUCTION FOR PERSIAN TEXT:
On the top header of the cream-colored official paper, print ONLY this exact short Persian title in bold, sharp, authentic right-to-left Iranian typography (Titr/Yekan style):
"{headline_persian}"
Do NOT add any extra body text or summary lines below the title. Ensure the Persian letters are properly connected, right-aligned, and completely legible --ar 9:16"""
    
    return prompt.strip()

def generate_story_image(prompt_text):
    """تلاش برای ساخت خودکار عکس در صورت پشتیبانی API"""
    gemini_image_models = [
        "gemini-2.0-flash-exp-image-generation",
        "gemini-2.5-flash-image-preview"
    ]
    for m_name in gemini_image_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]}
            }
            res = requests.post(url, json=payload, timeout=45)
            if res.status_code == 200:
                data = res.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        return base64.b64decode(part["inlineData"]["data"])
        except Exception:
            pass
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
        توجه بسیار مهم زمانی: ما اکنون در **آبان ماه سال ۱۴۰۵ خورشیدی (اکتبر ۲۰۲۶)** هستیم.
        
        متن ورودی:
        ---
        {item["text"]}
        ---

        شروط رد فوری (فقط کلمه REJECT_AD را خروجی بده):
        1. اگر متن هرگونه تبلیغ دوره، کارگاه، وبینار، نرم‌افزار، مشاوره یا نام مدرس دیگری است.
        2. اگر خبر منقضی‌شده و مربوط به سال‌های گذشته (مثل سال ۱۴۰۳ یا ۱۴۰۴) است و ارتباطی با سال جاری (۱۴۰۵) ندارد.
        3. اگر خبر گزارش عملکرد دولتی یا استانی بی‌فایده برای کسب‌وکارهاست.

        خروجی تو باید دقیقاً شامل ۲ بخش زیر باشد که با جداکننده ---HEADLINE--- از هم تفکیک شده‌اند:

        بخش اول - کپشن پست تلگرام:
        - لحن کاملاً کوتاه، خنثی، رسمی و دارای بولت‌پوینت‌های دقیق (•)
        - استخراج شماره بخشنامه، تاریخ‌ها و شرایط کلیدی
        - سال جاری **۱۴۰۵** است. هرگز سال را به ۱۴۰۴ یا ۱۴۰۳ تغییر نده.
        - خط اول: تیتر صریح و بولد با تگ <b>
        - خط آخر: 🌐 @EyvaziCoach
        - اصلاً از ستاره (*) استفاده نکن.

        ---HEADLINE---
        (فقط یک تیتر بسیار کوتاه ۳ تا ۵ کلمه‌ای فارسی بنویس که صرفاً موضوع اصلی خبر را بگوید تا روی سربرگ داخل عکس چاپ شود؛ بدون خلاصه کردن خبر)
        """
        try:
            response = text_model.generate_content(prompt)
            result = response.text.strip()
            
            if "REJECT_AD" in result or len(result) < 40:
                print(f"پست از {item['source']} به دلیل تبلیغاتی یا قدیمی بودن رد شد.")
                continue
                
            parts = result.split("---HEADLINE---")
            caption = parts[0].strip()
            headline = parts[1].strip() if len(parts) > 1 else "اطلاعیه رسمی مالیاتی"
            
            image_bytes = None
            if item.get("image_url"):
                try:
                    img_res = requests.get(item["image_url"], timeout=15)
                    if img_res.status_code == 200:
                        image_bytes = img_res.content
                except Exception:
                    pass

            image_prompt = build_editorial_prompt(headline)
            
            if not image_bytes:
                image_bytes = generate_story_image(image_prompt)
                
            return caption, image_bytes, image_prompt
            
        except Exception as e:
            print(f"Content generation error: {e}")
            break
            
    return None, None, None

def send_to_private_admin(caption, image_prompt, target_time_str):
    """ارسال متن خبر و پرامپت ساخت تصویر به چت خصوصی ادمین برای خبرهای فاقد عکس"""
    if not ADMIN_CHAT_ID:
        print("هشدار: متغیر ADMIN_CHAT_ID در گیت‌هاب تنظیم نشده است!")
        return

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # پیام اول: متن آماده کپشن
    msg_caption = f"📝 <b>پیش‌نویس خبر بدون تصویر (هدف: ساعت {target_time_str})</b>\n\n{caption}"
    requests.post(tg_url, data={"chat_id": ADMIN_CHAT_ID, "text": msg_caption, "parse_mode": "HTML"}, timeout=15)
    
    # پیام دوم: پرامپت آماده Nano Banana قابل کپی با یک لمس
    msg_prompt = (
        f"🎨 <b>پرامپت ساخت تصویر استوری (Editorial Flat Lay):</b>\n"
        f"<i>(روی متن زیر بزنید تا کپی شود)</i>\n\n"
        f"<code>{image_prompt}</code>"
    )
    res = requests.post(tg_url, data={"chat_id": ADMIN_CHAT_ID, "text": msg_prompt, "parse_mode": "HTML"}, timeout=15)
    print(f"ارسال پرامپت به چت خصوصی ادمین: Status {res.status_code}")

def send_to_channels(caption, image_bytes, schedule_date):
    """ارسال پست‌های دارای تصویر به کانال عمومی تلگرام و بله"""
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "caption": caption,
        "parse_mode": "HTML",
        "schedule_date": schedule_date
    }
    try:
        files = {"photo": ("story.jpg", io.BytesIO(image_bytes), "image/jpeg")}
        res = requests.post(tg_url, data=payload, files=files, timeout=25)
        print(f"Telegram Channel Photo Status: {res.status_code}")
    except Exception as e:
        print(f"Telegram Channel Error: {e}")

    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
        files = {"photo": ("story.jpg", io.BytesIO(image_bytes), "image/jpeg")}
        res_bale = requests.post(bale_url, data={"chat_id": BALE_CHAT, "caption": bale_caption}, files=files, timeout=25)
        print(f"Bale Channel Photo Status: {res_bale.status_code}")
    except Exception as e:
        print(f"Bale Channel Error: {e}")

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
    target_str = target_time.strftime('%H:%M')
    
    iran_tz = pytz.timezone('Asia/Tehran')
    print(f"اجرا در ساعت: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')} | زمان هدف: {target_str}")
    
    caption, image_bytes, image_prompt = generate_verified_package()
    if not caption:
        print("محتوای تاییدشده‌ای یافت نشد.")
        exit(0)
        
    if image_bytes:
        print("خبر دارای تصویر است؛ ارسال مستقیم به کانال‌ها...")
        send_to_channels(caption, image_bytes, schedule_timestamp)
    else:
        print("خبر فاقد تصویر است؛ ارسال متن و پرامپت ساخت تصویر به چت خصوصی ادمین...")
        send_to_private_admin(caption, image_prompt, target_str)
