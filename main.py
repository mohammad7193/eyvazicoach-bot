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

def get_latest_news(history):
    rss_urls = [
        "https://shenasname.ir/feed/",              
        "https://tejaratnews.com/feed/",            
        "https://www.eghtesadonline.com/fa/feeds/"  
    ]
    
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
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
        news_title, news_link, news_img = get_latest_news(history)
        if not news_title:
            print("خبر جدیدی یافت نشد. خروج از برنامه.")
            exit(0) 
            
        save_history(news_title)
        
        prompt = f"""
        You are a senior tax and accounting consultant writing a direct, high-value post for business managers on Telegram/Bale in Persian (Farsi).
        Topic: "خبر اقتصادی: {news_title}"
        
        STRICT CONTENT GUIDELINES:
        1. AVOID GENERALIZATIONS: Be highly specific and factual.
        2. NEWS ACCURACY: MUST stick exactly to the provided facts. DO NOT invent details.
        3. NO PROMOTIONS: ABSOLUTELY NO COURSE SELLING or MARKETING.
        4. Structure: 
           - Line 1: Strong news title with 1 relevant emoji.
           - Paragraph 1 (3-4 lines): News summary without fluff.
           - Paragraph 2 (1 short line): Key actionable advice based on the news.
           - Last line: @eyvazicoach
        5. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        6. Length: 60 to 90 words maximum.
        """
        response = model.generate_content(prompt)
        caption = response.text.strip()
        return post_type, caption, news_img
        
    elif post_type == "edu":
        recent_topics = "\n".join(history[-20:]) if history else "هیچ پستی تا الان منتشر نشده"
        
        prompt = f"""
        You are a senior Iranian tax, accounting, and business coach writing a post for managers on Telegram/Bale in Persian (Farsi).
        
        CRITICAL RULE 1 (ANTI-HALLUCINATION):
        DO NOT write specific numbers, deadlines (like 12 days or 21 days), exact penalty percentages, or specific article numbers of Iranian tax law. Your internal knowledge might be outdated.
        Instead, focus on universal business management, general accounting principles, cash-flow management, HR strategies, or the *conceptual* importance of compliance (e.g., "Why timely invoicing matters").

        CRITICAL RULE 2 (NO REPETITION):
        Do NOT write about any of these recently published topics:
        {recent_topics}
        
        STRICT CONTENT GUIDELINES:
        1. AVOID GENERALIZATIONS: Provide a practical, conceptual business tip.
        2. NO PROMOTIONS: ABSOLUTELY NO COURSE SELLING.
        3. Structure: 
           - Line 1: Strong conceptual title with 1 relevant emoji.
           - Paragraph 1 (3-4 lines): Conceptual explanation or business principle.
           - Paragraph 2 (1 short line): Key actionable management advice.
           - Last line: @eyvazicoach
        4. Formatting: Use <b>word</b> for emphasis. NEVER use markdown asterisks (*).
        5. Length: 60 to 90 words maximum.
        
        After the text, output exactly "---" on a new line.
        
        IMAGE QUERY RULES (CRITICAL):
        To prevent images with foreign currencies or foreign text, output EXACTLY ONE of the following safe keywords for Pexels. DO NOT write anything else:
        calculator
        laptop keyboard
        coffee mug
        blank notebook
        office plant
        """
        response = model.generate_content(prompt)
        content = response.text.split("---")
        caption = content[0].strip()
        image_query = content[1].strip() if len(content) > 1 else "calculator"
        
        generated_title = caption.split('\n')[0].replace('<b>', '').replace('</b>', '').strip()
        save_history(generated_title)
        
        return post_type, caption, image_query

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
        print(f"اجرای پست آموزشی. جستجوی پکسلز با کلمه: {resource}") 
        image_url = get_pexels_image(resource)
        send_post(caption, image_url=image_url)
