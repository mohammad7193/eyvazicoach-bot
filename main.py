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

# متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

genai.configure(api_key=GEMINI_API_KEY)
text_model = genai.GenerativeModel('gemini-3.6-flash')

HISTORY_FILE = "history.txt"

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
        
    old_years = ['۱۴۰۲', '1402', '۱۴۰۳', '1403']
    for old_y in old_years:
        if old_y in text and '۱۴۰۵' not in text and '1405' not in text:
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
                
                # استخراج دقیق عکس پست از تلگرام
                img_url = None
                photo_wrap = re.search(r'tgme_widget_message_photo_wrap.*?background-image:url\(\'([^\']+)\'\)', block)
                if photo_wrap:
                    raw_img = photo_wrap.group(1)
                    # فیلتر کردن ایموجی‌ها و استیکرها که اشتباهاً عکس تلقی نشوند
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
                        "image_url": img_url,
                        "hash": t_hash,
                        "source": f"@{ch}"
                    })
        except Exception as e:
            print(f"Error scraping @{ch}: {e}")
    return candidates

def generate_verified_package():
    history = load_history()
    candidates = get_intamedia_candidates(history) + scrape_telegram_candidates(history)
    
    if not candidates:
        return None, None

    for item in candidates[:3]:
        save_history(item["hash"])
        raw_full_text = item["text"]
        
        prompt = f"""
        نقش:
        تو ویراستار ارشد و کپی‌رایتر مالیاتی-مدیریتی برای برند «EyvaziCoach» هستی.
        توجه بسیار مهم زمانی: ما اکنون در **آبان ماه سال ۱۴۰۵ خورشیدی (اکتبر ۲۰۲۶)** هستیم.
        
        متن ورودی (متن کامل خبر):
        ---
        {raw_full_text}
        ---

        شروط رد فوری (فقط کلمه REJECT_AD را خروجی بده):
        1. اگر متن هرگونه تبلیغ دوره، کارگاه، وبینار، نرم‌افزار، مشاوره یا نام مدرس دیگری است.
        2. اگر خبر منقضی‌شده و مربوط به سال‌های گذشته (مثل سال ۱۴۰۳ یا ۱۴۰۴) است.

        خروجی تو باید شامل موارد زیر باشد:
        - **به هیچ وجه خبر را خلاصه نکن!** تمام جزئیات، پاراگراف‌ها، تبصره‌ها و متن کامل خبر اصلی باید حفظ شود.
        - فقط متن را از نظر نگارشی و املایی ویراستاری کن و لحن آن را به یک لحن رسمی، حرفه‌ای و رسانه‌ای تبدیل کن.
        - هرگونه لینک، آیدی تلگرام، یا اضافات تبلیغاتی کانال مبدا را حذف کن.
        - سال جاری **۱۴۰۵** است. هرگز سال را تغییر نده.
        - خط اول: تیتر صریح خبر به صورت بولد با تگ <b>
        - خط آخر: 🌐 @EyvaziCoach
        - اصلاً از ستاره (*) استفاده نکن.
        """
        try:
            response = text_model.generate_content(prompt)
            caption = response.text.strip()
            
            if "REJECT_AD" in caption or len(caption) < 40:
                print(f"پست از {item['source']} به دلیل تبلیغاتی یا قدیمی بودن رد شد.")
                continue
            
            # دانلود تصویر اصلی در صورت وجود
            image_bytes = None
            if item.get("image_url"):
                try:
                    img_res = requests.get(item["image_url"], timeout=15)
                    if img_res.status_code == 200:
                        image_bytes = img_res.content
                except Exception as e:
                    print(f"Error downloading original image from {item['image_url']}: {e}")
                    pass

            return caption, image_bytes
            
        except Exception as e:
            print(f"Content generation error: {e}")
            break
            
    return None, None

def send_to_private_admin(caption, target_time_str):
    """ارسال متن خبرهای فاقد عکس به چت خصوصی ادمین"""
    if not ADMIN_CHAT_ID:
        print("هشدار: متغیر ADMIN_CHAT_ID در گیت‌هاب تنظیم نشده است!")
        return

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    msg_caption = f"📝 <b>پیش‌نویس خبر بدون تصویر (هدف: ساعت {target_time_str})</b>\n\n{caption}"
    requests.post(tg_url, data={"chat_id": ADMIN_CHAT_ID, "text": msg_caption, "parse_mode": "HTML"}, timeout=15)
    print("ارسال پیام به چت خصوصی ادمین انجام شد.")

def send_to_channels(caption, image_bytes, schedule_date):
    """ارسال پست‌های دارای تصویر (اورجینال) به کانال عمومی تلگرام و بله"""
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
        requests.post(bale_url, data={"chat_id": BALE_CHAT, "caption": bale_caption}, files=files, timeout=25)
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
    
    caption, image_bytes = generate_verified_package()
    if not caption:
        print("محتوای تاییدشده‌ای یافت نشد.")
        exit(0)
        
    if image_bytes:
        print("خبر دارای تصویر اورجینال است؛ ارسال مستقیم به کانال‌ها...")
        send_to_channels(caption, image_bytes, schedule_timestamp)
    else:
        print("خبر فاقد تصویر است؛ ارسال متن به چت خصوصی ادمین...")
        send_to_private_admin(caption, target_str)
