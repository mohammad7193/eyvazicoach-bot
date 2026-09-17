import os
import requests
import datetime
import pytz
import random
import feedparser
import google.generativeai as genai

# دریافت ایمن متغیرهای محیطی
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

def get_latest_content(history, category="general"):
    # دسته‌بندی منابع بر اساس درخواست: منابع اصلی برای آموزش، و ترکیب منابع برای اخبار
    if category == "official_rules":
        rss_urls = [
            "https://www.intamedia.ir/rss",  # سازمان امور مالیاتی
            "https://news.tamin.ir/rss"      # سازمان تامین اجتماعی
        ]
    else:
        rss_urls = [
            "https://www.intamedia.ir/rss",
            "https://news.tamin.ir/rss",
            "https://tejaratnews.com/feed/",
            "https://shenasname.ir/feed/"
        ]
    
    random.shuffle(rss_urls) # جلوگیری از خواندن تکراری یک سایت خاص
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.title
                if title not in history:
                    image_url = extract_image_from_entry(entry)
                    return title, entry.link, image_url
        except Exception:
            continue 
            
    return None, None, None

def determine_post_type():
    iran_tz = pytz.timezone('Asia/Tehran')
    hour = datetime.datetime.now(iran_tz).hour
    
    if hour in [9, 10, 11, 15, 16, 17]:
        return "edu"
    else:
        return "news"

def generate_content():
    history = load_history()
    post_type = determine_post_type()
    
    if post_type == "news":
        news_title, news_link, news_img = get_latest_content(history, "general")
        if not news_title:
            print("خبر جدیدی یافت نشد. خروج از برنامه.")
            exit(0) 
            
        save_history(news_title)
        
        prompt = f"""
        You are an expert Iranian financial and social coach writing for Telegram/Bale in Persian (Farsi).
        Topic: "خبر جدید: {news_title}"
        
        TARGET AUDIENCE: General public, workers, employees, retirees, shopkeepers, and small business owners.
        
        STRICT CONTENT GUIDELINES:
        1. RELATABILITY: Explain this news simply. How does it affect ordinary people's lives, pockets, or small shops? Avoid heavy corporate jargon.
        2. ACCURACY: Base your text ONLY on the provided title. Do NOT invent numbers or deadlines.
        3. NO PROMOTIONS: ABSOLUTELY NO COURSE SELLING.
        4. Structure: 
           - Line 1: Catchy, relatable title with 1 emoji (e.g. 📰, 🛒, 🏢).
           - Paragraph 1 (3-4 lines): Simple summary of the news.
           - Paragraph 2 (1 short line): Practical advice or takeaway for the average person/worker.
           - Last line: @eyvazicoach
        5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        6. Length: 60 to 90 words maximum.
        """
        response = model.generate_content(prompt)
        caption = response.text.strip()
        return post_type, caption, news_img
        
    elif post_type == "edu":
        # دریافت قانون/بخشنامه جدید از تامین اجتماعی یا امور مالیاتی
        rule_title, rule_link, rule_img = get_latest_content(history, "official_rules")
        if not rule_title:
            print("قانون یا بخشنامه جدیدی یافت نشد. خروج از برنامه.")
            exit(0)
            
        save_history(rule_title)
        
        prompt = f"""
        You are a friendly Iranian legal/financial coach helping everyday people on Telegram/Bale in Persian (Farsi).
        Official Rule/Circular to explain: "{rule_title}"
        
        TARGET AUDIENCE: Workers, shopkeepers, employees, retirees, and everyday citizens.
        
        STRICT CONTENT GUIDELINES:
        1. SIMPLIFY THE LAW: Convert this dry official rule into a simple, practical educational tip. Explain what it means for a worker's rights, a shopkeeper's taxes, or a retiree's pension.
        2. NO HALLUCINATION: Rely ONLY on the premise of the provided rule. DO NOT invent tax percentages or penalty days.
        3. NO PROMOTIONS: ABSOLUTELY NO COURSE SELLING.
        4. Structure: 
           - Line 1: Engaging, clear title with 1 emoji (e.g. 💡, ☂️, ⚖️).
           - Paragraph 1 (3-4 lines): Simple explanation of the rule.
           - Paragraph 2 (1 short line): Actionable tip for the ordinary citizen or small business.
           - Last line: @eyvazicoach
        5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        6. Length: 60 to 90 words maximum.
        
        After the text, output exactly "---" on a new line.
        
        IMAGE QUERY RULES (CRITICAL):
        We need a visually neutral image that does NOT show foreign text, foreign money, or non-Iranian documents.
        Output EXACTLY ONE of the following safe keywords for Pexels. DO NOT write anything else:
        tea cup desk
        blank notebook pen
        simple calculator
        office plant
        empty meeting room
        """
        response = model.generate_content(prompt)
        content = response.text.split("---")
        caption = content[0].strip()
        
        # اگر خبر اصلی عکس داشته باشد، عکس ایرانی را استفاده می‌کنیم. در غیر این صورت پکسلز با کلمات امن.
        if rule_img:
            image_query = "USE_ORIGINAL_IMAGE"
        else:
            image_query = content[1].strip() if len(content) > 1 else "simple calculator"
            
        return post_type, caption, rule_img if rule_img else image_query

def get_pexels_image(query):
    if query == "USE_ORIGINAL_IMAGE":
        return None # نیازی به پکسلز نیست
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=15"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            random_photo = random.choice(response["photos"])
            return random_photo["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return "https://images.pexels.com/photos/53621/calculator-calculation-insurance-finance-53621.jpeg"

def send_post(caption, image_url=None):
    if image_url:
        try:
            img_response = requests.get(image_url, timeout=15)
            img_data = img_response.content
            tg_payload = {"chat_id": TELEGRAM_CHAT, "caption": caption, "parse_mode": "HTML"}
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            res_tg = requests.post(tg_url, data=tg_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
            print(f"Telegram Photo Status: {res_tg.status_code}")
        except Exception as e:
            print(f"Telegram Photo Error: {e}")
    else:
        try:
            tg_payload = {"chat_id": TELEGRAM_CHAT, "text": caption, "parse_mode": "HTML"}
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            res_tg = requests.post(tg_url, data=tg_payload)
            print(f"Telegram Text Status: {res_tg.status_code}")
        except Exception as e:
            print(f"Telegram Text Error: {e}")

    bale_caption = caption.replace('<b>', '').replace('</b>', '')
    if image_url:
        try:
            bale_payload = {"chat_id": BALE_CHAT, "photo": image_url, "caption": bale_caption}
            bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
            res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
            print(f"Bale Photo Status: {res_bale.status_code}")
        except Exception as e:
            print(f"Bale Photo Error: {e}")
    else:
        try:
            bale_payload = {"chat_id": BALE_CHAT, "text": bale_caption}
            bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
            res_bale = requests.post(bale_url, data=bale_payload, timeout=20)
            print(f"Bale Text Status: {res_bale.status_code}")
        except Exception as e:
            print(f"Bale Text Error: {e}")

if __name__ == "__main__":
    post_type, caption, resource = generate_content()
    
    if post_type == "news":
        print(f"اجرای پست خبری. عکس همراه خبر: {resource}")
        send_post(caption, image_url=resource)
    else:
        if resource and resource.startswith("http"):
            print(f"اجرای پست آموزشی. استفاده از عکس رسمی سایت.")
            send_post(caption, image_url=resource)
        else:
            print(f"اجرای پست آموزشی. جستجوی پکسلز با کلمه خنثی: {resource}") 
            image_url = get_pexels_image(resource)
            send_post(caption, image_url=image_url)
