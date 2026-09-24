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

def is_relevant_news(title):
    allowed_keywords = [
        'مالیات', 'بیمه', 'حقوق', 'دستمزد', 'کارگر', 'کارفرما', 'قانون کار', 
        'اصناف', 'کسب', 'چک', 'بانک', 'وام', 'تسهیلات', 'بورس', 'تجارت', 
        'مودیان', 'یارانه', 'بازنشسته', 'تامین اجتماعی', 'اداره کار', 'مالی', 
        'تورم', 'بازار', 'اقتصاد', 'قیمت', 'گمرک', 'صادرات'
    ]
    forbidden_keywords = [
        'ترامپ', 'آمریکا', 'اسرائیل', 'غزه', 'جنگ', 'مدرسه', 'مدارس', 'دانش‌آموز',
        'سیاسی', 'انتخابات', 'قطر', 'ورزش', 'فوتبال', 'سینما', 'قتل', 'حوادث', 'تصادف'
    ]
    
    for bad_word in forbidden_keywords:
        if bad_word in title:
            return False
            
    for good_word in allowed_keywords:
        if good_word in title:
            return True
            
    return False

def get_latest_content(history, category="general"):
    if category == "official_rules":
        rss_urls = [
            "https://www.intamedia.ir/rss",
            "https://news.tamin.ir/rss"
        ]
    else:
        rss_urls = [
            "https://www.intamedia.ir/rss",
            "https://news.tamin.ir/rss",
            "https://tejaratnews.com/feed/",
            "https://shenasname.ir/feed/"
        ]
    
    random.shuffle(rss_urls)
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.title
                if title not in history:
                    if category == "general" and not is_relevant_news(title):
                        continue
                        
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
            print("خبر اقتصادی/مالیاتی جدیدی یافت نشد. خروج از برنامه.")
            exit(0) 
            
        save_history(news_title)
        
        prompt = f"""
        You are a professional and eloquent Iranian financial journalist writing for Telegram/Bale in Persian (Farsi).
        Topic: "خبر: {news_title}"
        
        STRICT CONTENT GUIDELINES:
        1. TONE & STYLE: Write beautifully, naturally, and smoothly. DO NOT act like a preacher or advisor. NEVER use forced labels like "پیامد:" (Consequence) or "راهکار:" (Solution). Just report the news and its context fluidly.
        2. RESPECTFUL & DIGNIFIED: Maintain a highly professional, dignified tone. DO NOT use exaggerated portrayals of poverty, distress, or misery when discussing economic news.
        3. ACCURACY: Base your text ONLY on the provided title. Do NOT invent numbers or facts.
        4. CONCISENESS: Keep the caption brief and punchy. Avoid verbose explanations. (Max 60-70 words).
        5. Structure: 
           - Line 1: Catchy, natural title with 1 relevant emoji.
           - Body: 1 or 2 cohesive paragraphs seamlessly delivering the news.
           - Last line: @eyvazicoach
        6. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        """
        response = model.generate_content(prompt)
        caption = response.text.strip()
        return post_type, caption, news_img
        
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
        2. RESPECTFUL & DIGNIFIED: Keep the tone dignified and professional. Avoid overly dramatic or distressing language about the economy or businesses.
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
