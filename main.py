import os
import requests
import datetime
import pytz
import random
import feedparser
import re
import google.generativeai as genai

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
    history = history[-100:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for item in history:
            f.write(item + "\n")

def extract_image_from_entry(entry):
    if hasattr(entry, 'enclosures'):
        for enc in entry.enclosures:
            if 'type' in enc and 'image' in enc['type']:
                return enc['href']
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
    if hasattr(entry, 'links'):
        for link in entry.links:
            if 'type' in link and 'image' in link['type']:
                return link['href']
    return None

def get_og_image(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=12)
        match = re.search(r'property=[\'"]og:image[\'"]\s+content=[\'"]([^\'"]+)[\'"]', resp.text, re.IGNORECASE)
        if not match:
            match = re.search(r'content=[\'"]([^\'"]+)[\'"]\s+property=[\'"]og:image[\'"]', resp.text, re.IGNORECASE)
        if not match:
            match = re.search(r'<img[^>]+src=[\'"]([^\'"]+)[\'"][^>]+itemprop=[\'"]image[\'"]', resp.text, re.IGNORECASE)
        if match:
            img_url = match.group(1)
            if not img_url.startswith("http"):
                if "mehrnews" in url:
                    img_url = "https://www.mehrnews.com" + img_url
                elif "khabarfoori" in url:
                    img_url = "https://www.khabarfoori.com" + img_url
            return img_url
    except Exception as e:
        print(f"Error fetching OG image: {e}")
    return None

def is_entry_fresh(entry):
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        pub_time = datetime.datetime(*entry.published_parsed[:6], tzinfo=pytz.utc)
        now_utc = datetime.datetime.now(pytz.utc)
        if (now_utc - pub_time).total_seconds() > 48 * 3600:
            return False
    return True

def is_relevant_news(title):
    forbidden_keywords = [
        'طلا', 'سکه', 'دلار', 'ارز', 'گوشت', 'مرغ', 'ترافیک', 'جاده', 'آب و هوا',
        'مدارس', 'تعطیلی', 'گازوئیل', 'بنزین', 'نفت', 'عراق', 'انگلیس', 'آمریکا',
        'ترامپ', 'جنگ', 'اسرائیل', 'غزه', 'قتل', 'تصادف', 'حوادث', 'ورزش', 
        'فوتبال', 'سینما', 'بازیگر', 'خودرو', 'بورس', 'دیوان عدالت', 'سکو',
        'پروژه', 'تحقق', 'درآمد مالیاتی', 'استان', 'استاندار', 'شهردار', 'مجلس',
        'فرماندار', 'افتتاح', 'نشست', 'همایش', 'مراسم', 'دیدار', 'بودجه', 'وزیر',
        'گزارش عملکرد', 'توسعه', 'تامین مالی', 'میزان وصول'
    ]
    allowed_keywords = [
        'مالیات', 'بیمه', 'حقوق', 'دستمزد', 'کارگر', 'کارفرما', 'قانون کار', 
        'اصناف', 'کسب و کار', 'چک', 'بانک', 'وام', 'تسهیلات', 'تجارت', 
        'مودیان', 'بازنشسته', 'تامین اجتماعی', 'اداره کار', 'اظهارنامه',
        'بخشنامه', 'حسابداری', 'استخدام', 'یارانه', 'سامانه مودیان', 'معافیت'
    ]
    for bad in forbidden_keywords:
        if bad in title:
            return False
    for good in allowed_keywords:
        if good in title:
            return True
    return False

def is_news_valuable(title):
    try:
        iran_tz = pytz.timezone('Asia/Tehran')
        today_date = datetime.datetime.now(iran_tz).strftime('%Y-%m-%d')
        prompt = f"""
        تو سردبیر یک رسانه تحلیلی اقتصادی-مالیاتی هستی. تاریخ امروز: {today_date}.
        تیتر خبر: "{title}"
        
        دو شرط اجباری:
        1. خبر نباید منقضی، قدیمی یا مربوط به مهلت‌های گذشته (مثل ماه‌های قبل) باشد.
        2. خبر باید اثر عملی، قانونی یا مالی مستقیم برای مودیان، اصناف، کارگران یا شرکت‌ها داشته باشد (گزارش‌کارهای اداری و دولتی رد شوند).
        
        آیا این خبر تایید است؟ فقط بنویس: YES یا NO
        """
        response = model.generate_content(prompt)
        return "YES" in response.text.upper()
    except Exception:
        return False

def get_latest_content(history, category="general"):
    if category == "official_rules":
        rss_urls = ["https://www.intamedia.ir/rss", "https://news.tamin.ir/rss"]
        random.shuffle(rss_urls)
        for url in rss_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:8]:
                    title = entry.title
                    if title in history:
                        continue
                    if not is_entry_fresh(entry):
                        continue
                    image_url = extract_image_from_entry(entry)
                    if not image_url:
                        image_url = get_og_image(entry.link)
                    return title, entry.link, image_url
            except Exception:
                continue 
        return None, None, None
    else:
        sources = [
            ("https://www.mehrnews.com/tag/%D8%B3%D8%A7%D8%B2%D9%85%D8%A7%D9%86+%D8%A7%D9%85%D9%88%D8%B1+%D9%85%D8%A7%D9%84%DB%8C%D8%A7%D8%AA%DB%8C", "mehr"),
            ("https://www.khabarfoori.com/%D8%A8%D8%AE%D8%B4-%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF%DB%8C-145", "khabarfoori")
        ]
        random.shuffle(sources)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        for url, source_name in sources:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                html = resp.text
                news_list = []
                
                # خواندن فقط ۵ خبر اول هر صفحه برای جلوگیری از نفوذ به اخبار آرشیوی گذشته
                if source_name == "mehr":
                    matches = re.findall(r'<a href="(/news/\d+/[^"]+)"[^>]*>(.*?)</a>', html)
                    for link, title in matches[:6]:
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        if len(title) > 20:
                            news_list.append((title, "https://www.mehrnews.com" + link))
                elif source_name == "khabarfoori":
                    matches = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', html)
                    for link, title in matches[:8]:
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        if len(title) > 20 and ('/بخش-' in link or '/fa/tiny/' in link or '/detail/' in link):
                            if not link.startswith("http"):
                                link = "https://www.khabarfoori.com" + link
                            news_list.append((title, link))
                
                for title, link in news_list:
                    if not is_relevant_news(title):
                        continue
                    if title not in history and is_news_valuable(title):
                        image_url = get_og_image(link)
                        return title, link, image_url
            except Exception as e:
                print(f"Scraping error: {e}")
                continue
        return None, None, None

def generate_content(post_type):
    history = load_history()
    
    if post_type == "news":
        news_title, news_link, news_img = get_latest_content(history, "general")
        if not news_title:
            return None, None
            
        save_history(news_title)
        
        prompt = f"""
        You are a professional Iranian financial journalist writing for Telegram/Bale in Persian.
        Topic: "خبر: {news_title}"
        
        STRICT CONTENT GUIDELINES:
        1. TONE & STYLE: Write clearly and naturally. Do NOT act like a preacher. NEVER use forced labels.
        2. ACCURACY: Base your text ONLY on the provided title. Do NOT invent numbers or facts.
        3. CONCISENESS: Keep it brief and punchy. (Max 60-70 words).
        4. Structure: 
           - Line 1: Catchy title with 1 relevant emoji.
           - Body: 1 or 2 cohesive paragraphs delivering the factual news context.
           - Last line: @eyvazicoach
        5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        """
        response = model.generate_content(prompt)
        caption = response.text.strip()
        resource = news_img if news_img else "TEXT_ONLY"
        return caption, resource
        
    elif post_type == "edu":
        rule_title, rule_link, rule_img = get_latest_content(history, "official_rules")
        if not rule_title:
            return None, None
            
        save_history(rule_title)
        
        prompt = f"""
        You are a professional Iranian legal/financial analyst writing for Telegram/Bale in Persian.
        Official Rule to explain: "{rule_title}"
        
        STRICT CONTENT GUIDELINES:
        1. TONE & STYLE: Write clearly and naturally. Do NOT use forced labels. Blend the explanation smoothly.
        2. ACCURACY: Rely ONLY on the premise of the provided rule. DO NOT invent tax percentages or deadlines.
        3. CONCISENESS: Keep it brief and concise. (Max 60-70 words).
        4. Structure: 
           - Line 1: Engaging title with 1 emoji.
           - Body: 1 or 2 cohesive paragraphs explaining the practical rule simply.
           - Last line: @eyvazicoach
        5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        
        After the text, output exactly "---" on a new line.
        
        IMAGE QUERY RULES:
        Output EXACTLY ONE safe keyword for Pexels if needed:
        cup of black tea on desk
        blank open notebook
        minimalist office plant
        white computer keyboard
        """
        response = model.generate_content(prompt)
        content = response.text.split("---")
        caption = content[0].strip()
        
        if rule_img:
            resource = rule_img
        else:
            resource = content[1].strip() if len(content) > 1 else "blank open notebook"
            
        return caption, resource

def get_pexels_image(query):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        if "photos" in response and len(response["photos"]) > 0:
            random_photo = random.choice(response["photos"])
            return random_photo["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return "https://images.pexels.com/photos/317355/pexels-photo-317355.jpeg"

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
    
    schedule = [
        (10, "edu"),
        (13, "news"),
        (16, "edu"),
        (19, "news")
    ]
    
    for target_hour, p_type in schedule:
        target_time = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now < target_time:
            return p_type, target_time
            
    target_time = now.replace(hour=10, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return "edu", target_time

if __name__ == "__main__":
    post_type, target_time = get_next_target()
    schedule_timestamp = int(target_time.timestamp())
    
    iran_tz = pytz.timezone('Asia/Tehran')
    print(f"اجرا در ساعت: {datetime.datetime.now(iran_tz).strftime('%H:%M:%S')}")
    print(f"درحال آماده‌سازی محتوا برای ساعت هدف {target_time.strftime('%H:%M:%S')}...")
    
    caption, resource = generate_content(post_type)
    
    if not caption:
        print("هیچ خبر معتبر، جدید و مرتبطی یافت نشد. خروج از برنامه.")
        exit(0)
        
    if resource == "TEXT_ONLY":
        print("ارسال خبر بدون تصویر به شکل متنی...")
        send_post(caption, image_url=None, schedule_date=schedule_timestamp)
    elif resource and resource.startswith("http"):
        print(f"ارسال با تصویر اصلی استخراج‌شده از خبرگزاری: {resource}")
        send_post(caption, image_url=resource, schedule_date=schedule_timestamp)
    else:
        print(f"ارسال با تصویر پکسلز: {resource}")
        image_url = get_pexels_image(resource)
        send_post(caption, image_url=image_url, schedule_date=schedule_timestamp)
