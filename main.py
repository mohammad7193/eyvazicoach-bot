import os
import requests
import datetime
import pytz
import random
import feedparser
import re
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

def is_relevant_news(title):
    # لیست سیاه قطعی: اخبار زرد و بی‌ربطی که مخاطب را فراری می‌دهد
    forbidden_keywords = [
        'طلا', 'سکه', 'دلار', 'ارز', 'گوشت', 'مرغ', 'ترافیک', 'جاده', 'آب و هوا',
        'مدارس', 'تعطیلی', 'گازوئیل', 'بنزین', 'نفت', 'عراق', 'انگلیس', 'آمریکا',
        'ترامپ', 'جنگ', 'اسرائیل', 'غزه', 'قتل', 'تصادف', 'حوادث', 'ورزش', 
        'فوتبال', 'سینما', 'بازیگر', 'خودرو', 'بورس', 'دیوان عدالت', 'سکو'
    ]
    
    # لیست سفید: کلماتی که تایید می‌کنند خبر کاملا تخصصی و بدردبخور است
    allowed_keywords = [
        'مالیات', 'بیمه', 'حقوق', 'دستمزد', 'کارگر', 'کارفرما', 'قانون کار', 
        'اصناف', 'کسب و کار', 'چک', 'بانک', 'وام', 'تسهیلات', 'تجارت', 
        'مودیان', 'بازنشسته', 'تامین اجتماعی', 'اداره کار', 'اظهارنامه',
        'بخشنامه', 'حسابداری', 'استخدام', 'یارانه', 'اقتصاد', 'مالی'
    ]
    
    for bad in forbidden_keywords:
        if bad in title:
            return False
            
    for good in allowed_keywords:
        if good in title:
            return True
            
    return False

def get_latest_content(history, category="general"):
    if category == "official_rules":
        # منابع پست‌های آموزشی: فقط منابع صد در صد رسمی
        rss_urls = [
            "https://www.intamedia.ir/rss",
            "https://news.tamin.ir/rss"
        ]
        random.shuffle(rss_urls)
        for url in rss_urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.title
                    if title not in history:
                        image_url = extract_image_from_entry(entry)
                        return title, entry.link, image_url
            except Exception:
                continue 
        return None, None, None
    else:
        # منابع پست‌های خبری: فقط لینک‌های درخواستی کاربر با استفاده از Web Scraping
        sources = [
            ("https://www.mehrnews.com/tag/%D8%B3%D8%A7%D8%B2%D9%85%D8%A7%D9%86+%D8%A7%D9%85%D9%88%D8%B1+%D9%85%D8%A7%D9%84%DB%8C%D8%A7%D8%AA%DB%8C", "mehr"),
            ("https://www.khabarfoori.com/%D8%A8%D8%AE%D8%B4-%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF%DB%8C-145", "khabarfoori")
        ]
        random.shuffle(sources)
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        for url, source_name in sources:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                html = resp.text
                
                news_list = []
                # استخراج لینک‌ها از سورس HTML سایت‌ها
                if source_name == "mehr":
                    matches = re.findall(r'<a href="(/news/\d+/[^"]+)"[^>]*>(.*?)</a>', html)
                    for link, title in matches:
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        if len(title) > 20:
                            news_list.append((title, "https://www.mehrnews.com" + link))
                            
                elif source_name == "khabarfoori":
                    matches = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', html)
                    for link, title in matches:
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        if len(title) > 20 and ('/بخش-' in link or '/fa/tiny/' in link or '/detail/' in link):
                            if not link.startswith("http"):
                                link = "https://www.khabarfoori.com" + link
                            news_list.append((title, link))
                
                # فیلترینگ شدید برای جلوگیری از اخبار زرد
                for title, link in news_list:
                    if not is_relevant_news(title):
                        continue
                        
                    if title not in history:
                        # چون اسکرپ کردیم، عکس خبر استخراج نمی‌شود، تا پکسلز عکس خنثی بدهد
                        return title, link, None 
                        
            except Exception as e:
                print(f"Scraping error: {e}")
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
            print("خبر اقتصادی/مالیاتی جدیدی یافت نشد. خروج از برنامه.")
            exit(0) 
            
        save_history(news_title)
        
        prompt = f"""
        You are a professional and eloquent Iranian financial journalist writing for Telegram/Bale in Persian (Farsi).
        Topic: "خبر: {news_title}"
        
        STRICT CONTENT GUIDELINES:
        1. TONE & STYLE: Write beautifully, naturally, and smoothly. DO NOT act like a preacher or advisor. NEVER use forced labels like "پیامد:" or "راهکار:". Just report the news and its context fluidly.
        2. RESPECTFUL & DIGNIFIED: Maintain a highly professional, dignified tone.
        3. ACCURACY: Base your text ONLY on the provided title. Do NOT invent numbers or facts.
        4. CONCISENESS: Keep the caption brief and punchy. Avoid verbose explanations. (Max 60-70 words).
        5. Structure: 
           - Line 1: Catchy, natural title with 1 relevant emoji.
           - Body: 1 or 2 cohesive paragraphs seamlessly delivering the news.
           - Last line: @eyvazicoach
        6. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        
        After the text, output exactly "---" on a new line.
        
        IMAGE QUERY RULES:
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
        image_query = content[1].strip() if len(content) > 1 else "simple calculator"
        
        return post_type, caption, image_query
        
    elif post_type == "edu":
        rule_title, rule_link, rule_img = get_latest_content(history, "official_rules")
        if not rule_title:
            print("قانون یا بخشنامه جدیدی یافت نشد. خروج از برنامه.")
            exit(0)
            
        save_history(rule_title)
        
        prompt = f"""
        You are a professional Iranian legal/financial analyst writing for Telegram/Bale in Persian (Farsi).
        Official Rule/Circular to explain: "{rule_title}"
        
        STRICT CONTENT GUIDELINES:
        1. TONE & STYLE: Write beautifully, clearly, and naturally. DO NOT use forced labels like "راهکار:" (Advice) or "نتیجه:" (Result). Blend the explanation smoothly.
        2. RESPECTFUL & DIGNIFIED: Keep the tone dignified and professional. 
        3. NO HALLUCINATION: Rely ONLY on the premise of the provided rule. DO NOT invent tax percentages, deadlines, or penalty days.
        4. CONCISENESS: Keep it brief and concise. Avoid lengthy or verbose sentences. (Max 60-70 words).
        5. Structure: 
           - Line 1: Engaging, clear title with 1 emoji.
           - Body: 1 or 2 cohesive paragraphs explaining the rule simply.
           - Last line: @eyvazicoach
        6. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        
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
        
        if rule_img:
            image_query = "USE_ORIGINAL_IMAGE"
        else:
            image_query = content[1].strip() if len(content) > 1 else "simple calculator"
            
        return post_type, caption, rule_img if rule_img else image_query

def get_pexels_image(query):
    if query == "USE_ORIGINAL_IMAGE":
        return None 
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
        print(f"اجرای پست خبری. جستجوی پکسلز با کلمه خنثی: {resource}")
        image_url = get_pexels_image(resource)
        send_post(caption, image_url=image_url)
    else:
        if resource and resource.startswith("http"):
            print(f"اجرای پست آموزشی. استفاده از عکس رسمی سایت.")
            send_post(caption, image_url=resource)
        else:
            print(f"اجرای پست آموزشی. جستجوی پکسلز با کلمه خنثی: {resource}") 
            image_url = get_pexels_image(resource)
            send_post(caption, image_url=image_url)
