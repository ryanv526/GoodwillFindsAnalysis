import os
import requests
import json
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from urllib.parse import quote
from pathlib import Path
import time
import google.generativeai as genai
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# --- CONFIG (Environment Variables) ---
SECRET_KEY = os.getenv("SGW_SECRET_KEY", "6696D2E6F042FEC4D6E3F32AD541143B")
IV = os.getenv("SGW_IV", "0000000000000000")
USER = os.getenv("SGW_USER")
PASS = os.getenv("SGW_PASS")

# API Keys loaded from .env (comma-separated list)
api_keys_raw = os.getenv("GEMINI_API_KEYS", "")
API_KEYS = [key.strip() for key in api_keys_raw.split(",") if key.strip()]

# Models to rotate between
MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash"
]

# Email Configuration
EMAIL_CONFIG = {
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", 587)),
    "sender_email": os.getenv("EMAIL_SENDER"),
    "sender_password": os.getenv("EMAIL_APP_PASSWORD"),
    "recipient_email": os.getenv("EMAIL_RECIPIENT")
}

class APIRotator:
    """Manages rotation between API keys and models"""
    def __init__(self, api_keys, models):
        self.api_keys = api_keys
        self.models = models
        self.current_key_index = 0
        self.current_model_index = 0
        self.requests_per_key = {i: 0 for i in range(len(api_keys))}
        
    def get_next_config(self):
        """Get next API key and model combination"""
        api_key = self.api_keys[self.current_key_index]
        model = self.models[self.current_model_index]
        self.requests_per_key[self.current_key_index] += 1
        self.current_model_index = (self.current_model_index + 1) % len(self.models)
        if self.current_model_index == 0:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return api_key, model
    
    def get_usage_report(self):
        """Get current usage stats"""
        total = sum(self.requests_per_key.values())
        report = f"Total Requests: {total}/{len(self.api_keys)*40}\n"
        for i, count in self.requests_per_key.items():
            report += f"  API Key {i+1}: {count}/40\n"
        return report

def sgw_encrypt(text):
    """Encrypt text using AES CBC mode - UTF-8 key version"""
    key_bytes = SECRET_KEY.encode('utf-8')
    iv_bytes = IV.encode('utf-8')
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv_bytes)
    encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return quote(base64.b64encode(encrypted).decode('utf-8'))

def download_image(url, filename, session):
    """Download an image from a URL"""
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
        return False
    except Exception as e:
        return False

def resize_image_for_tokens(image_path, max_size=(800, 800)):
    """Resize to maximize images per request while staying under limits"""
    try:
        img = Image.open(image_path)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        print(f"    Warning: Could not resize {image_path}: {e}")
        return Image.open(image_path)

def analyze_item_single_request(item_data, api_key, model_name):
    """SINGLE REQUEST ANALYSIS using specified API key and model"""
    try:
        title = item_data.get('title', 'Unknown')
        price = item_data.get('price', 0)
        image_paths = item_data.get('local_paths', [])
        
        if not image_paths:
            return {"error": "No images available"}
        
        total_images = len(image_paths)
        print(f"    🤖 Analysis: {total_images} images | Model: {model_name}")
        
        if total_images > 900:
            print(f"       ⚠️ Warning: {total_images} images exceeds 900 limit, using first 900")
            image_paths = image_paths[:900]
        
        pil_images = []
        for img_path in image_paths:
            try:
                resized_img = resize_image_for_tokens(Path(img_path), max_size=(800, 800))
                pil_images.append(resized_img)
            except Exception:
                pass
        
        if not pil_images:
            return {"error": "Could not load images"}
        
        genai.configure(api_key=api_key)
        
        prompt = f"""You are a professional card trader analyzing: "{title}" at ${price}

I'm sending {len(pil_images)} images. Your goal: MAXIMIZE PROFIT.

**CRITICAL ANALYSIS REQUIREMENTS:**

1. **IDENTIFY HIGH-VALUE CARDS ONLY** ($20+ threshold):
   - Player name, Year, Set, Card #, Parallel/Insert type
   - Current SOLD price (eBay sold listings, not asking prices)
   - Condition grade (PSA 10/9/8 equivalent or raw NM/LP/MP)
   - List EVERY card worth $20+, ignore bulk cards

2. **PROFIT CALCULATION**:
   - Total estimated value (conservative, assume one grade lower than appears)
   - Listing price: ${price}
   - Fees & shipping costs: ~15% of sales + ${price * 0.15:.2f} to acquire
   - Time to sell: estimate weeks/months
   - **NET PROFIT = (Total Value × 0.85) - ${price} - Selling Time Cost**

3. **RED FLAGS - CRITICAL**:
   - Fake/counterfeit indicators (centering, print quality, holo pattern)
   - Water damage, creases, edge wear reducing value 50%+
   - Overgraded conditions (sellers lie)
   - Hard-to-move inventory (obscure players, damaged stars)
   - Is this a "picked" lot? (all good cards already removed)

4. **RECOMMENDATION** (choose ONE):
   - **STRONG BUY**: Expected profit $100+, low risk, fast sell
   - **BUY**: Expected profit $50-100, moderate risk
   - **MAYBE**: Profit $20-50 OR high risk/slow sell
   - **PASS**: Profit under $20 or too much risk
   - **STRONG PASS**: Guaranteed loss or obvious scam

5. **ACTION PLAN** (if BUY/STRONG BUY):
   - Which specific cards to grade (PSA/BGS)
   - Quick flip vs hold strategy
   - Where to sell (eBay, COMC, local shop)
   - Maximum bid price (if auction)

**RESPONSE FORMAT:**
Start with: "[RECOMMENDATION]: $XX profit expected"
Then detailed breakdown.

Focus on REAL profit after fees, not theoretical card value. Be ruthless about condition and selling difficulty."""
        
        model = genai.GenerativeModel(model_name)
        
        try:
            response = model.generate_content(
                [prompt] + pil_images,
                generation_config={"temperature": 0.3, "max_output_tokens": 4000}
            )
            
            evaluation = {
                "title": title,
                "listing_price": price,
                "item_url": item_data.get('item_url'),
                "total_images": len(pil_images),
                "full_analysis": response.text,
                "api_key_used": api_key[-10:],
                "model_used": model_name,
                "api_requests_used": 1
            }
            print(f"    ✅ Complete")
            return evaluation
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                print(f"       ⚠️ Rate limited on this key!")
                return {"error": "rate_limited", "message": str(e)}
            print(f"       Error: {e}")
            return {"error": str(e)}
    except Exception as e:
        print(f"    ❌ Analysis failed: {e}")
        return {"error": str(e)}

def extract_recommendation(analysis_text):
    """Extract buy recommendation and key details from analysis"""
    lines = analysis_text.split('\n')
    recommendation = "UNKNOWN"
    for line in lines:
        upper_line = line.upper()
        if any(x in upper_line for x in ['RECOMMENDATION', 'STRONG BUY', 'STRONG PASS', 'BUY', 'PASS', 'MAYBE']):
            if 'STRONG BUY' in upper_line: recommendation = "STRONG BUY"
            elif 'STRONG PASS' in upper_line: recommendation = "STRONG PASS"
            elif 'BUY' in upper_line and 'PASS' not in upper_line: recommendation = "BUY"
            elif 'PASS' in upper_line: recommendation = "PASS"
            elif 'MAYBE' in upper_line: recommendation = "MAYBE"
            break
    
    estimated_value = "Unknown"
    for line in lines:
        if 'TOTAL' in line.upper() and ('VALUE' in line.upper() or 'ESTIMATE' in line.upper()):
            estimated_value = line.strip()
            break
    return recommendation, estimated_value

def send_email_summary(evaluations, api_rotator):
    """Send email with ranked recommendations"""
    try:
        ranked = []
        for eval in evaluations:
            if 'error' in eval: continue
            analysis = eval.get('full_analysis', '')
            recommendation, estimated_value = extract_recommendation(analysis)
            
            score = {"STRONG BUY": 5, "BUY": 4, "MAYBE": 3, "PASS": 2, "STRONG PASS": 1}.get(recommendation, 0)
            
            ranked.append({
                "title": eval.get('title'),
                "price": eval.get('listing_price'),
                "url": eval.get('item_url'),
                "recommendation": recommendation,
                "estimated_value": estimated_value,
                "score": score,
                "analysis": analysis
            })
        
        ranked.sort(key=lambda x: x['score'], reverse=True)
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"ShopGoodwill Analysis - {len(ranked)} Items - {datetime.now().strftime('%Y-%m-%d')}"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['recipient_email']
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .strong-buy {{ background-color: #d4edda; border-left: 4px solid #28a745; }}
                .buy {{ background-color: #d1ecf1; border-left: 4px solid #17a2b8; }}
                .maybe {{ background-color: #fff3cd; border-left: 4px solid #ffc107; }}
                .pass {{ background-color: #f8d7da; border-left: 4px solid #dc3545; }}
                .strong-pass {{ background-color: #e2e3e5; border-left: 4px solid #6c757d; }}
                .item {{ margin: 20px 0; padding: 15px; border-radius: 5px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .stats {{ background-color: #f8f9fa; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header"><h1>🎴 Daily ShopGoodwill Analysis</h1><p>{datetime.now().strftime('%B %d, %Y')}</p></div>
            <div class="stats">
                <h2>📊 Summary</h2>
                <p><strong>Items Analyzed:</strong> {len(ranked)}</p>
                {api_rotator.get_usage_report().replace(chr(10), '<br>')}
            </div>
            <h2>🏆 Recommendations</h2>
        """
        for i, item in enumerate(ranked, 1):
            rec_class = item['recommendation'].lower().replace(' ', '-')
            key_points = (item['analysis'][:500] + "...").replace('\n', '<br>')
            html += f"""
            <div class="item {rec_class}">
                <h3>#{i}. {item['title']}</h3>
                <p><strong>Price:</strong> ${item['price']} | <strong>Recommendation:</strong> {item['recommendation']}</p>
                <p><strong>{item['estimated_value']}</strong></p>
                <p><a href="{item['url']}">View Listing →</a></p>
                <details><summary>Key Analysis</summary><p>{key_points}</p></details>
            </div>"""
        html += "</body></html>"
        msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        print(f"✅ Email sent to {EMAIL_CONFIG['recipient_email']}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

def get_all_images_for_item(item_id, session, token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
    try:
        url = f"https://buyerapi.shopgoodwill.com/api/ItemDetail/GetItemDetailModelByItemId/{item_id}"
        response = session.get(url, headers=headers, timeout=10)
        data = response.json()
        image_server = data.get('imageServer', 'https://shopgoodwillimages.azureedge.net/production/')
        image_url_string = data.get('imageUrlString', '')
        if not image_url_string: return []
        return [f"{image_server}{p.strip().replace('\\', '/')}" for p in image_url_string.split(';') if p.strip()]
    except: return []

def run_hunter(search_term="pokemon card", max_items=80, download_images=True):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Content-Type": "application/json"})
    api_rotator = APIRotator(API_KEYS, MODELS)
    
    print("🔐 Logging in...")
    login_payload = {"userName": sgw_encrypt(USER), "password": sgw_encrypt(PASS), "browser": "chrome"}
    try:
        auth_res = session.post("https://buyerapi.shopgoodwill.com/api/SignIn/Login", json=login_payload, timeout=10)
        token = auth_res.json().get("accessToken")
        
        print(f"\n📡 Searching for '{search_term}'...")
        search_payload = {"searchText": search_term, "pageSize": str(max_items), "sortColumn": "1"}
        search_res = session.post("https://buyerapi.shopgoodwill.com/api/Search/ItemListing", 
                                  json=search_payload, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        items = search_res.json().get('searchResults', {}).get('items', [])
        
        img_dir = Path("shopgoodwill_images")
        img_dir.mkdir(exist_ok=True)
        
        results, ai_evaluations = [], []
        for i, item in enumerate(items, 1):
            item_id = item.get('itemId')
            title = item.get('title', 'No title')
            price = item.get('currentPrice', 0)
            
            print(f"{'='*70}\n[{i}/{len(items)}] {title[:55]}\nID: {item_id} | Price: ${price}")
            
            all_images = get_all_images_for_item(item_id, session, token)
            item_data = {'item_id': item_id, 'title': title, 'price': price, 'item_url': f"https://shopgoodwill.com/item/{item_id}", 'local_paths': []}
            
            if download_images and all_images:
                item_folder = img_dir / f"{item_id}"
                item_folder.mkdir(exist_ok=True)
                for idx, img_url in enumerate(all_images, 1):
                    filename = item_folder / f"image_{idx}.jpg"
                    if download_image(img_url, filename, session):
                        item_data['local_paths'].append(str(filename))
                    time.sleep(0.1)
            
            if item_data['local_paths']:
                api_key, model = api_rotator.get_next_config()
                evaluation = analyze_item_single_request(item_data, api_key, model)
                if 'error' not in evaluation:
                    ai_evaluations.append(evaluation)
                    rec, val = extract_recommendation(evaluation['full_analysis'])
                    print(f"  📊 {rec} | {val}")
                time.sleep(2)
            results.append(item_data)
        
        with open('shopgoodwill_results.json', 'w') as f: json.dump(results, f, indent=2)
        send_email_summary(ai_evaluations, api_rotator)
        return results
    except Exception as e:
        print(f"❌ Error: {e}")
    return None

if __name__ == "__main__":
    run_hunter(search_term="pokemon card", max_items=80)