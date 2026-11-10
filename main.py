import os
import requests
import datetime
import pytz
import random
import feedparser
import re
import hashlib
import io
import google.generativeai as genai

# دریافت متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")  # استفاده از کلید پکسلز شما برای عکس‌های جایگزین
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

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
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'09\d{9}', '', text)
    text = re.sub(r'۰۹[۰-۹]{9}', '', text)
    text = re.sub(r'/[^\s]+$', '', text) # حذف امضاهای خبری مثل /ایسنا یا /زومان در انتهای متن
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def is_clean_and_relevant(text):
    if len(text) < 60:
        return False
        
    old_years = ['۱۴۰۲', '1402', '۱۴۰۳', '1403']
    for old_y in old_years:
        if old_y in text and '۱۴۰۵' not in text and '1405' not in text:
            return False

    ad_keywords = [
        'دوره', 'کارگاه', 'وبینار', 'سمینار', 'ثبت نام', 'ثبت‌نام', 'شهریه', 
        'تخفیف', 'ظرفیت', 'استاد', 'مدرس', 'پکیج', 'فروش', 'خرید', 'مشاوره', 
        'تماس بگیرید', 'شماره تماس', 'لینک زیر', 'کلیک کنید', 'استخدام', 'رزومه',
        'همکاری', 'کانال ما', 'پیج', 'اینستاگرام', 'واتساپ', 'هدیه',
        'قرعه کشی', 'قرعه‌کشی', 'اسپانسر', 'تبلیغات', 'کد معرف', 'آکادمی', 'موسسه'
    ]
    for bad in ad_keywords:
        if bad in text:
            return False
            
    # کلمات کلیدی جامع (مالیاتی + بانکی + اقتصاد کلان)
    valid_keywords = [
        'مالیات', 'ارزش افزوده', 'مودیان', 'سامانه مودیان', 'اظهارنامه', 'بخشنامه',
        'پایانه فروشگاهی', 'جرایم', 'جریمه', 'کارفرما', 'کارگر', 'دستمزد', 'بیمه', 'دیوان عدالت', 
        'ساتنا', 'پایا', 'سامانه پل', 'بانک مرکزی', 'سقف تراکنش', 'کف مبلغ',
        'رشد اقتصادی', 'تولید ناخالص', 'اقتصاد ایران', 'تورم', 'تسهیلات', 'حساب تجاری', 'چک صیادی'
    ]
    return any(k in text for k in valid_keywords)

def extract_article_image_and_body(url, base_domain=""):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None, ""
        html = resp.text
        
        img_url = None
        match = re.search(r'property=[\'"]og:image[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html, re.IGNORECASE)
        if not match:
            match = re.search(r'content=[\'"]([^\'"]+)[\'"]\s+property=[\'"]og:image[\'"]', html, re.IGNORECASE)
        if match:
            raw_img = match.group(1).strip()
            if raw_img.startswith("//"):
                img_url = "https:" + raw_img
            elif raw_img.startswith("/") and base_domain:
                img_url = base_domain.rstrip("/") + raw_img
            elif raw_img.startswith("http"):
                img_url = raw_img

        paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', html)
        valid_paras = []
        for p in paragraphs:
            clean_p = clean_raw_text(p)
            if len(clean_p) > 40 and not any(x in clean_p for x in ['کلیه حقوق', 'انتهای پیام', 'اخبار مرتبط']):
                valid_paras.append(clean_p)
                
        body_text = "\n\n".join(valid_paras[:6])
        return img_url, body_text
    except Exception as e:
        print(f"Error extracting article {url}: {e}")
        return None, ""

def get_intamedia_candidates(history):
    candidates = []
    rss_urls = ["https://www.intamedia.ir/rss", "https://www.intamedia.ir/news/rss"]
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.title.strip()
                t_hash = get_text_hash(title)
                if t_hash in history:
                    continue
                
                img_url = None
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    raw_img = entry.enclosures[0].get('href', '')
                    if raw_img.startswith('http'):
                        img_url = raw_img
                        
                page_img, page_body = extract_article_image_and_body(entry.link, "https://www.intamedia.ir")
                if not img_url:
                    img_url = page_img
                    
                summary = clean_raw_text(getattr(entry, 'summary', ''))
                full_text = f"{title}\n{summary}\n{page_body}".strip()
                
                if is_clean_and_relevant(full_text):
                    candidates.append({"text": full_text, "image_url": img_url, "hash": t_hash, "source": "intamedia.ir"})
        except Exception as e:
            print(f"Intamedia error: {e}")
    return candidates

def scrape_telegram_candidates(history):
    # کانال‌های اقتصادی و مالیاتی جامع به همراه eskannews
    target_channels = ["ecoiran_com", "Econ_Fouri", "taxpress", "rahbarhesab", "taxinformation", "eskannews_com"]
    random.shuffle(target_channels)
    candidates = []
    
    for ch in target_channels:
        try:
            resp = requests.get(f"https://t.me/s/{ch}", headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
                
            message_blocks = re.findall(r'<div class="tgme_widget_message_wrap[^"]*">([\s\S]*?)</div>\s*</div>\s*</div>', resp.text)
            for block in reversed(message_blocks[-10:]):
                
                img_url = None
                photo_wrap = re.search(r'tgme_widget_message_photo_wrap[\s\S]*?background-image:url\(\'([^\']+)\'\)', block)
                if photo_wrap:
                    raw_img = photo_wrap.group(1)
                    if 'emoji' not in raw_img and not raw_img.endswith('.svg'):
                        if raw_img.startswith('//'):
                            img_url = 'https:' + raw_img
                        elif raw_img.startswith('http'):
                            img_url = raw_img
                
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
                        "image_url": img_url, # ممکنه None باشه، که بعداً با Pexels جبران میشه
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
    return candidates

def get_pexels_fallback_image():
    """اگر خبر عکس نداشت، یک عکس فاخر مدیریتی/مالی از Pexels برمی‌دارد"""
    if not PEXELS_API_KEY:
        return None
    try:
        queries = ["office desk flat lay", "business desktop", "minimalist office dark", "financial newspaper"]
        query = random.choice(queries)
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=15&orientation=portrait"
        headers = {"Authorization": PEXELS_API_KEY}
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            photos = res.json().get("photos", [])
            if photos:
                photo = random.choice(photos)
                img_url = photo["src"]["large"]
                img_res = requests.get(img_url, timeout=10)
                if img_res.status_code == 200:
                    print("عکس جایگزین با موفقیت از Pexels دانلود شد.")
                    return img_res.content
    except Exception as e:
        print(f"Pexels Error: {e}")
    return None

def download_valid_image(url):
    if not url: return None
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200 and len(res.content) > 5000:
            return res.content
    except Exception:
        pass
    return None

def generate_verified_package():
    history = load_history()
    candidates = get_intamedia_candidates(history) + scrape_telegram_candidates(history)
    
    if not candidates:
        return None, None

    for item in candidates[:4]:
        save_history(item["hash"])
        raw_full_text = item["text"]
        
        prompt = f"""
        نقش:
        تو سردبیر ارشد مالی، مالیاتی و اقتصادی برای برند «EyvaziCoach» هستی. ما در سال ۱۴۰۵ هستیم.
        
        متن ورودی (متن خام خبر):
        ---
        {raw_full_text[:2500]}
        ---

        شروط رد فوری (فقط بنویس REJECT_AD):
        1. اگر متن تبلیغ دوره، وبینار، نرم‌افزار، یا نام مدرس دیگری است.
        2. اگر خبر مربوط به سال‌های گذشته (مثل ۱۴۰۳) است.

        دستورالعمل نگارش کپشن تلگرام:
        - **به هیچ وجه اعداد، مبالغ بانکی (ساتنا، پایا و...)، یا درصدهای اقتصادی را حذف یا خلاصه نکن!** این داده‌ها حیاتی هستند.
        - لحن را به یک گزارش رسمی، شیک و حرفه‌ای رسانه‌ای تبدیل کن و غلط‌های نگارشی را برطرف کن.
        - مبالغ و شرایط کلیدی را حتماً در قالب بولت‌پوینت‌های خوانا (•) لیست کن تا صاحبان کسب‌وکار راحت بخوانند.
        - هرگونه نام خبرگزاری (مثل ایسنا، زومان و...) یا لینک مبدا را حذف کن.
        - خط اول: 📌 + تیتر صریح و جذاب خبر به صورت بولد با تگ <b>
        - خط آخر: 🌐 @EyvaziCoach
        """
        try:
            response = text_model.generate_content(prompt)
            caption = response.text.strip()
            
            if "REJECT_AD" in caption or len(caption) < 40:
                print(f"پست از {item['source']} توسط هوش مصنوعی رد شد.")
                continue
            
            # ۱. تلاش برای دانلود عکس اصلی خبر
            image_bytes = download_valid_image(item["image_url"])
            
            # ۲. اگر عکس نداشت، دانلود خودکار از Pexels
            if not image_bytes:
                print("خبر عکس نداشت، در حال دریافت عکس جایگزین از Pexels...")
                image_bytes = get_pexels_fallback_image()
            
            print(f"خبر معتبر از منبع {item['source']} تایید و آماده شد.")
            return caption, image_bytes
            
        except Exception as e:
            print(f"Content generation error: {e}")
            break
            
    return None, None

def send_to_channels(caption, image_bytes, schedule_date):
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto" if image_bytes else f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "parse_mode": "HTML",
        "schedule_date": schedule_date
    }
    
    # ارسال به تلگرام
    try:
        if image_bytes:
            payload["caption"] = caption
            files = {"photo": ("news_image.jpg", io.BytesIO(image_bytes), "image/jpeg")}
            res = requests.post(tg_url, data=payload, files=files, timeout=25)
        else:
            payload["text"] = caption
            res = requests.post(tg_url, data=payload, timeout=25)
        print(f"Telegram Channel Status: {res.status_code}")
    except Exception as e:
        print(f"Telegram Channel Error: {e}")

    # ارسال به بله
    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto" if image_bytes else f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
        
        if image_bytes:
            files = {"photo": ("news_image.jpg", io.BytesIO(image_bytes), "image/jpeg")}
            requests.post(bale_url, data={"chat_id": BALE_CHAT, "caption": bale_caption}, files=files, timeout=25)
        else:
            requests.post(bale_url, data={"chat_id": BALE_CHAT, "text": bale_caption}, timeout=25)
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
    print(f"اجرا در ساعت: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')} | زمان هدف انتشار: {target_str}")
    
    caption, image_bytes = generate_verified_package()
    if not caption:
        print("هیچ خبر جدیدی در این نوبت یافت نشد. خروج.")
        exit(0)
        
    send_to_channels(caption, image_bytes, schedule_timestamp)
