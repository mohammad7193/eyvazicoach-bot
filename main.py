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
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def is_clean_and_relevant(text):
    if len(text) < 60:
        return False
        
    # فیلتر اخبار سال‌های گذشته
    old_years = ['۱۴۰۲', '1402', '۱۴۰۳', '1403']
    for old_y in old_years:
        if old_y in text and '۱۴۰۵' not in text and '1405' not in text:
            return False

    # فیلتر تبلیغات، دوره‌ها و اخبار تشریفاتی دولتی
    ad_keywords = [
        'دوره', 'کارگاه', 'وبینار', 'سمینار', 'ثبت نام', 'ثبت‌نام', 'شهریه', 
        'تخفیف', 'ظرفیت', 'استاد', 'مدرس', 'پکیج', 'فروش', 'خرید', 'مشاوره', 
        'تماس بگیرید', 'شماره تماس', 'لینک زیر', 'کلیک کنید', 'استخدام', 'رزومه',
        'همکاری', 'کانال ما', 'پیج', 'اینستاگرام', 'واتساپ', 'تلگرام', 'هدیه',
        'رایگان', 'قرعه کشی', 'قرعه‌کشی', 'اسپانسر', 'تبلیغات', 'معرفی کتاب',
        'نرم افزار', 'نرم‌افزار', 'دمو', 'جشنواره', 'کد معرف', 'آکادمی', 'موسسه',
        'پروژه', 'تحقق', 'درآمد مالیاتی', 'استاندار', 'شهردار', 'فرماندار', 'افتتاح', 'نشست'
    ]
    for bad in ad_keywords:
        if bad in text:
            return False
            
    valid_keywords = [
        'مالیات', 'ارزش افزوده', 'مودی', 'مؤدی', 'مودیان', 'سامانه مودیان', 
        'اظهارنامه', 'بخشنامه', 'تبصره', 'ماده', 'معافیت', 'پایانه فروشگاهی', 
        'جرایم', 'جریمه', 'صورتحساب', 'الکترونیکی', 'کارفرما', 'کارگر', 
        'حقوق', 'دستمزد', 'بیمه', 'تامین اجتماعی', 'دیوان عدالت', 'دادنامه', 'چک', 'اصناف'
    ]
    return any(k in text for k in valid_keywords)

def extract_article_image_and_body(url, base_domain=""):
    """باز کردن صفحه خبر در سایت‌ها و استخراج همزمان عکس شاخص (og:image) و متن کامل مقاله"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None, ""
        html = resp.text
        
        # ۱. استخراج تصویر شاخص
        img_url = None
        match = re.search(r'property=[\'"]og:image[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html, re.IGNORECASE)
        if not match:
            match = re.search(r'content=[\'"]([^\'"]+)[\'"]\s+property=[\'"]og:image[\'"]', html, re.IGNORECASE)
        if not match:
            match = re.search(r'<img[^>]+src=[\'"]([^\'"]+)[\'"][^>]+itemprop=[\'"]image[\'"]', html, re.IGNORECASE)
            
        if match:
            raw_img = match.group(1).strip()
            if raw_img.startswith("//"):
                img_url = "https:" + raw_img
            elif raw_img.startswith("/") and base_domain:
                img_url = base_domain.rstrip("/") + raw_img
            elif raw_img.startswith("http"):
                img_url = raw_img

        # ۲. استخراج پاراگراف‌های متن خبر برای جلوگیری از ناقص بودن متن
        paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', html)
        valid_paras = []
        for p in paragraphs:
            clean_p = clean_raw_text(p)
            if len(clean_p) > 40 and not any(x in clean_p for x in ['کلیه حقوق', 'انتهای پیام', 'اخبار مرتبط', 'عضویت در']):
                valid_paras.append(clean_p)
                
        body_text = "\n\n".join(valid_paras[:6])
        return img_url, body_text
    except Exception as e:
        print(f"Error extracting article {url}: {e}")
        return None, ""

def get_intamedia_candidates(history):
    """رصد سایت رسمی سازمان امور مالیاتی (فقط اخبار دارای عکس)"""
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
                    
                # قانون طلایی: بدون عکس = رد فوری
                if not img_url:
                    continue
                    
                summary = clean_raw_text(getattr(entry, 'summary', ''))
                full_text = f"{title}\n{summary}\n{page_body}".strip()
                
                if is_clean_and_relevant(full_text):
                    candidates.append({
                        "text": full_text,
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": "intamedia.ir"
                    })
        except Exception as e:
            print(f"Intamedia error: {e}")
    return candidates

def get_news_websites_candidates(history):
    """رصد سایت‌های تخصصی اقتصادی که همیشه عکس باکیفیت دارند (اکوایران، کاماپرس، تجارت‌نیوز)"""
    candidates = []
    
    # ۱. فیدهای RSS مستقیم سایت‌های تخصصی
    rss_sources = [
        ("https://www.tejaratnews.com/feed", "https://www.tejaratnews.com", "tejaratnews.com"),
        ("https://kamapress.com/feed", "https://kamapress.com", "kamapress.com"),
        ("https://www.eghtesadonline.com/fa/rss/allnews", "https://www.eghtesadonline.com", "eghtesadonline.com")
    ]
    random.shuffle(rss_sources)
    
    for rss_url, domain, name in rss_sources:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:12]:
                title = entry.title.strip()
                if not is_clean_and_relevant(title):
                    continue
                t_hash = get_text_hash(title)
                if t_hash in history:
                    continue
                    
                img_url, body_text = extract_article_image_and_body(entry.link, domain)
                if not img_url:
                    continue
                    
                summary = clean_raw_text(getattr(entry, 'summary', ''))
                full_text = f"{title}\n{summary}\n{body_text}".strip()
                
                if is_clean_and_relevant(full_text):
                    candidates.append({
                        "text": full_text,
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": name
                    })
        except Exception as e:
            print(f"RSS error ({name}): {e}")

    # ۲. اسکرپ مستقیم صفحه اختصاصی مالیات اکوایران
    try:
        eco_url = "https://ecoiran.com/%D8%A8%D8%AE%D8%B4-%D9%85%D8%A7%D9%84%DB%8C%D8%A7%D8%AA-94"
        resp = requests.get(eco_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            matches = re.findall(r'<a[^>]+href="(/news/\d+[^"]*)"[^>]*>([\s\S]*?)</a>', resp.text)
            for link, raw_title in matches[:8]:
                title = clean_raw_text(raw_title)
                if len(title) < 25:
                    continue
                t_hash = get_text_hash(title)
                if t_hash in history:
                    continue
                    
                full_link = "https://ecoiran.com" + link
                img_url, body_text = extract_article_image_and_body(full_link, "https://ecoiran.com")
                if not img_url:
                    continue
                    
                full_text = f"{title}\n{body_text}".strip()
                if is_clean_and_relevant(full_text):
                    candidates.append({
                        "text": full_text,
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": "ecoiran.com"
                    })
    except Exception as e:
        print(f"Ecoiran scrape error: {e}")

    return candidates

def scrape_telegram_candidates(history):
    """رصد کانال‌های تلگرامی مرجع - فقط و فقط پست‌هایی که عکس واقعی دارند"""
    target_channels = ["ecoiran_com", "Econ_Fouri", "taxpress", "rahbarhesab", "taxinformation"]
    random.shuffle(target_channels)
    candidates = []
    
    for ch in target_channels:
        try:
            resp = requests.get(f"https://t.me/s/{ch}", headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
                
            message_blocks = re.findall(r'<div class="tgme_widget_message_wrap[^"]*">([\s\S]*?)</div>\s*</div>\s*</div>', resp.text)
            for block in reversed(message_blocks[-10:]):
                
                # استخراج دقیق عکس پست از تلگرام
                img_url = None
                photo_wrap = re.search(r'tgme_widget_message_photo_wrap[\s\S]*?background-image:url\(\'([^\']+)\'\)', block)
                if photo_wrap:
                    raw_img = photo_wrap.group(1)
                    if 'emoji' not in raw_img and not raw_img.endswith('.svg'):
                        if raw_img.startswith('//'):
                            img_url = 'https:' + raw_img
                        elif raw_img.startswith('http'):
                            img_url = raw_img
                
                # قانون طلایی: اگر پست تلگرامی عکس نداشت، فوراً رد شود
                if not img_url:
                    continue
                
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
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
    return candidates

def download_valid_image(url):
    """دانلود تصویر و اطمینان از اینکه فایل واقعاً یک عکس معتبر است"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200 and len(res.content) > 5000:
            return res.content
    except Exception as e:
        print(f"Image download failed ({url}): {e}")
    return None

def generate_verified_package():
    history = load_history()
    
    # تجمیع کاندیداهای عکس‌دار (اولویت اول: سایت مالیاتی و سایت‌های تخصصی، اولویت دوم: کانال‌های عکس‌دار)
    candidates = (
        get_intamedia_candidates(history) + 
        get_news_websites_candidates(history) + 
        scrape_telegram_candidates(history)
    )
    
    if not candidates:
        return None, None

    for item in candidates[:4]:
        # ابتدا مطمئن می‌شویم عکس خبر واقعاً قابل دانلود است
        image_bytes = download_valid_image(item["image_url"])
        if not image_bytes:
            continue
            
        save_history(item["hash"])
        raw_full_text = item["text"]
        
        prompt = f"""
        نقش:
        تو ویراستار ارشد و کپی‌رایتر مالیاتی-مدیریتی برای برند «EyvaziCoach» هستی.
        توجه بسیار مهم زمانی: ما اکنون در **آبان ماه سال ۱۴۰۵ خورشیدی (نوامبر ۲۰۲۶)** هستیم.
        
        متن ورودی (متن کامل خبر):
        ---
        {raw_full_text[:2500]}
        ---

        شروط رد فوری (فقط کلمه REJECT_AD را خروجی بده):
        1. اگر متن هرگونه تبلیغ دوره، کارگاه، وبینار، نرم‌افزار، مشاوره یا نام مدرس دیگری است.
        2. اگر خبر منقضی‌شده و مربوط به سال‌های گذشته (مثل سال ۱۴۰۳ یا ۱۴۰۴) است.
        3. اگر خبر گزارش عملکرد دولتی یا استانی بی‌فایده است و هیچ اثر عملی برای صاحبان کسب‌وکار، حسابداران یا مردم ندارد.

        دستورالعمل خروجی (در صورت تایید خبر):
        - **به هیچ وجه خبر را خلاصه نکن!** تمام جزئیات، اعداد، بخشنامه‌ها، پاراگراف‌ها و تبصره‌های متن اصلی باید به صورت کامل و جامع نوشته شوند.
        - فقط متن را از نظر نگارشی و املایی ویراستاری کن و لحن آن را به یک لحن رسمی، حرفه‌ای و رسانه‌ای تبدیل کن.
        - توجه: کپشن عکس در تلگرام حداکثر ۱۰۲۴ کاراکتر جا دارد؛ بنابراین کل متن خبر را بدون حذف نکات مهم در حدود ۱۲۰ تا ۱۵۰ کلمه تنظیم کن تا در کپشن تلگرام کامل جا شود.
        - هرگونه لینک، نام خبرگزاری یا آیدی تلگرام مبدا را حذف کن.
        - سال جاری **۱۴۰۵** است. هرگز سال را تغییر نده.
        - خط اول: 📌 + تیتر صریح خبر به صورت بولد با تگ <b>
        - خط آخر: 🌐 @EyvaziCoach
        - اصلاً از ستاره (*) استفاده نکن.
        """
        try:
            response = text_model.generate_content(prompt)
            caption = response.text.strip()
            
            if "REJECT_AD" in caption or len(caption) < 40:
                print(f"پست از {item['source']} توسط هوش مصنوعی رد شد.")
                continue
            
            print(f"خبر معتبر همراه با تصویر از منبع {item['source']} تایید شد.")
            return caption, image_bytes
            
        except Exception as e:
            print(f"Content generation error: {e}")
            break
            
    return None, None

def send_to_channels(caption, image_bytes, schedule_date):
    """ارسال مستقیم پست عکس‌دار به کانال عمومی تلگرام و بله"""
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "caption": caption,
        "parse_mode": "HTML",
        "schedule_date": schedule_date
    }
    try:
        files = {"photo": ("news_image.jpg", io.BytesIO(image_bytes), "image/jpeg")}
        res = requests.post(tg_url, data=payload, files=files, timeout=25)
        print(f"Telegram Channel Photo Status: {res.status_code}")
    except Exception as e:
        print(f"Telegram Channel Error: {e}")

    try:
        bale_caption = caption.replace('<b>', '').replace('</b>', '')
        bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
        files = {"photo": ("news_image.jpg", io.BytesIO(image_bytes), "image/jpeg")}
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
    print(f"اجرا در ساعت: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')} | زمان هدف انتشار: {target_str}")
    
    caption, image_bytes = generate_verified_package()
    if not caption or not image_bytes:
        print("هیچ خبر عکس‌دار جدیدی در این نوبت یافت نشد. خروج.")
        exit(0)
        
    send_to_channels(caption, image_bytes, schedule_timestamp)
