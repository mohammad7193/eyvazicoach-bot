import os
import requests
import datetime
import pytz
import google.generativeai as genai

# دریافت متغیرهای محیطی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
BALE_TOKEN = os.environ.get("BALE_BOT_TOKEN")
BALE_CHAT = os.environ.get("BALE_CHAT_ID")

# تنظیم مدل جمینای
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')

def get_current_topic():
    iran_tz = pytz.timezone('Asia/Tehran')
    hour = datetime.datetime.now(iran_tz).hour

    if hour < 9:
         return "یک پست صبح بخیر پرانرژی. یادآوری نعمت‌هایی که خدا به ما داده و شکرگزاری بابت زندگی. **قانون بسیار مهم:** به هیچ وجه، تحت هیچ شرایطی کلماتی مثل پول، مالیات، بیمه، حسابداری یا کسب‌وکار در این پست استفاده نشود."
    elif hour < 12:
         return "یک پست تخصصی و کاربردی درباره مسائل و قوانین مالیاتی."
    elif hour < 15:
         return "آموزش کاربردی حسابداری برای مدیران."
    elif hour < 18:
         return "نکات کلیدی در مورد سامانه مودیان یا قوانین بیمه پرسنل."
    else:
         return "تکنیک‌های مدیریت هزینه‌های کسب‌وکار یا زندگی شخصی."

def generate_content(topic):
    prompt = f"""
    You are an expert content creator for "Eyvazi Coach", a financial, tax, and accounting consulting firm.
    Write a Persian (Farsi) microblog post based strictly on this topic: {topic}
    
    CRITICAL RULES:
    1. NEVER use markdown asterisks (*) for bolding. If you need to emphasize a word, use HTML tags like <b>word</b>.
    2. Format: A catchy hook title (with an emoji), 3 to 4 lines of practical explanation, and a very short conclusion.
    3. Length: Maximum 70 to 100 words. Keep paragraphs short and scannable.
    4. At the very end of the text, on a new line, add exactly: @eyvazicoach
    
    After the Persian text, output exactly three dashes "---" on a new line.
    Then, provide a 1 to 3 words English search query for the Pexels API to find a high-quality, realistic image matching the post context.
    """
    
    response = model.generate_content(prompt)
    content = response.text.split("---")
    
    caption = content[0].strip()
    image_query = content[1].strip() if len(content) > 1 else "business lifestyle"
    
    return caption, image_query

def get_pexels_image(query):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(url, headers=headers, timeout=10).json()
        
        if "photos" in response and len(response["photos"]) > 0:
            return response["photos"][0]["src"]["large"]
    except Exception as e:
        print(f"Pexels Error: {e}")
    return None

def send_post(caption, image_url):
    try:
        # دانلود تصویر در رم سرور
        img_response = requests.get(image_url, timeout=15)
        img_data = img_response.content
        
        # تعریف ساختار استاندارد فایل برای ارسال (الزامی برای بله)
        files_payload = {
            "photo": ("image.jpg", img_data, "image/jpeg")
        }
        
        # ==========================================
        # ۱. ارسال به تلگرام (پشتیبانی از HTML)
        # ==========================================
        try:
            tg_payload = {
                "chat_id": TELEGRAM_CHAT,
                "caption": caption,
                "parse_mode": "HTML"
            }
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            response_tg = requests.post(tg_url, data=tg_payload, files=files_payload)
            print(f"Telegram Response: {response_tg.status_code}")
        except Exception as e:
            print(f"Telegram Error: {e}")

        # ==========================================
        # ۲. ارسال به بله (پشتیبانی فقط از متن/Markdown اختصاصی)
        # ==========================================
        try:
            # پاک‌سازی تگ‌های HTML برای جلوگیری از چاپ عینی تگ‌ها در بله
            bale_caption = caption.replace('<b>', '').replace('</b>', '')
            
            # دقت کن که parse_mode اینجا ارسال نمی‌شود
            bale_payload = {
                "chat_id": BALE_CHAT,
                "caption": bale_caption
            }
            
            bale_url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendPhoto"
            # ارسال مجدد متغیر files_payload به همراه نام و فرمت عکس
            response_bale = requests.post(bale_url, data=bale_payload, files={"photo": ("image.jpg", img_data, "image/jpeg")})
            print(f"Bale Response: {response_bale.status_code}")
            
            # اگر خطایی داد، متن ارور بله را چاپ کند تا دقیق متوجه شویم
            if response_bale.status_code != 200:
                print(f"Bale Error Detail: {response_bale.text}")
                
        except Exception as e:
            print(f"Bale Error: {e}")

    except Exception as e:
        print(f"General Posting Error: {e}")

if __name__ == "__main__":
    topic = get_current_topic()
    caption, query = generate_content(topic)
    
    image_url = get_pexels_image(query)
    if not image_url:
        image_url = get_pexels_image("office desk") # تصویر جایگزین
        
    send_post(caption, image_url)
