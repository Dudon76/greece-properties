import os
import re
import json
import time
import base64
import requests
import streamlit as st
import pandas as pd
from PIL import Image
from datetime import datetime
import google.generativeai as genai

# ==========================================
# 1. הגדרות בסיסיות ותצורת עמוד
# ==========================================
st.set_page_config(
    page_title="השקעות נדל\"ן ביוון - משפחת אנשל",
    page_icon="🏠",
    layout="wide"
)

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")
FILE_PATH = "properties_data.json"

# ==========================================
# מנגנון שמירה מול GitHub
# ==========================================
def get_github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def load_data():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        if "local_db" not in st.session_state:
            st.session_state.local_db = []
        return st.session_state.local_db

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
        res = requests.get(url, headers=get_github_headers(), timeout=10)
        if res.status_code == 200:
            content = res.json()
            file_data = base64.b64decode(content["content"]).decode("utf-8")
            st.session_state["file_sha"] = content["sha"]
            parsed_json = json.loads(file_data)
            
            # בדיקת השלמת תאריכים רטרואקטיבית לנכסים ישנים
            today_str = datetime.now().strftime("%Y-%m-%d")
            updated = False
            if isinstance(parsed_json, list):
                for item in parsed_json:
                    if "created_at" not in item or not item["created_at"]:
                        item["created_at"] = today_str
                        updated = True
                if updated:
                    save_data(parsed_json)
            return parsed_json if isinstance(parsed_json, list) else []
        else:
            return st.session_state.get("local_db", [])
    except Exception as e:
        return st.session_state.get("local_db", [])

def save_data(data_list):
    st.session_state.local_db = data_list
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
        json_bytes = json.dumps(data_list, ensure_ascii=False, indent=2).encode("utf-8")
        base64_content = base64.b64encode(json_bytes).decode("utf-8")

        payload = {
            "message": "Update properties database",
            "content": base64_content
        }
        if "file_sha" in st.session_state:
            payload["sha"] = st.session_state["file_sha"]

        res = requests.put(url, json=payload, headers=get_github_headers(), timeout=10)
        if res.status_code in [200, 201]:
            st.session_state["file_sha"] = res.json()["content"]["sha"]
    except Exception as e:
        st.error(f"שגיאה בשמירה ל-GitHub: {e}")

# ==========================================
# פונקציית בדיקת התאמה לקריטריוני התיעדוף
# ==========================================
def evaluate_ideal_criteria(prop):
    reasons = []

    loc_text = f"{prop.get('region', '')} {prop.get('city_town', '')} {prop.get('village', '')} {prop.get('summary', '')} {prop.get('property_title', '')}".lower()
    
    apokoronas_villages = [
        "apokoronas", "אפוקורונס", 
        "kalyves", "קליבס", "קאליבס", "tsivaras", "ציוואראס", "stylos", "סטילוס", "provarma", "פרווארמה", "armenoi", "ארמנוי", "ramni", "ראמני", "neo chorio", "ניאו כוריו",
        "almyrida", "אלמירידה", "plaka", "פלאקה", "kokkino chorio", "קוקינו", "kambia", "קמביה", "aspro", "אספרו", "drapanos", "דראפנוס", "palailoni", "פלאילוני", "vamos", "ואמוס", "gavalochori", "גובאלוכורי", "xirosterni", "קסירוסטרני", "kefalas", "קפלאס", "קפאלאס", "likotinarea", "ליקוטינארה", "sellia", "סליה",
        "paidochori", "פאיידוכורי", "kares", "קארס", "pemonia", "פמוניה", "meidochori", "מיידוכורי", "fres", "פרס",
        "nippos", "ניפוס", "vryses", "וריסס", "kalamitsi alexandrou", "קלאמיצי אלכסנדרו", "kalamitsi amygdali", "קלאמיצי אמגידאלי", "emprosneros", "אמפרוסנרוס", "vatoudiaris", "ואטוודיאריס", "kryonerida", "קריונרידה", "vafe", "ואפה", "vatos", "ואטוס",
        "asprouliani", "אספרוליאני", "filaki", "פילאקי", "metamorfosi", "מטמורפוסי", "mouri", "מורי", "mathes", "מאתס", "georgioupoli", "georgioupolis", "גאורגיופוליס", "kavros", "קאברוס", "lake kournas", "kournas", "קורנאס", "kastellos", "קסטלוס",
        "maza", "מזה", "alikampos", "אליקמפוס", "asi gonia", "אסי גוניה"
    ]
    
    is_apokoronas = any(v in loc_text for v in apokoronas_villages)
    if not is_apokoronas:
        reasons.append("מחוץ לאזור אפוקורונס")

    bedrooms = int(prop.get("bedrooms", 0) or 0)
    if bedrooms < 3:
        reasons.append(f"פחות מ-3 חדרי שינה ({bedrooms} חדרים)")

    built_sqm = float(prop.get("built_sqm", 0) or 0)
    if 0 < built_sqm < 80:
        reasons.append(f"שטח בנוי מתחת ל-80 מ\"ר ({built_sqm} מ\"ר)")

    physical_score = float(prop.get("physical_score", 5.0) or 5.0)
    if physical_score < 7.0:
        reasons.append("דורש שיפוץ/שדרוג")

    plot_sqm = float(prop.get("plot_sqm", 0) or 0)
    if 0 < plot_sqm < 200:
        reasons.append(f"חצר קטנה מ-200 מ\"ר ({plot_sqm} מ\"ר)")

    has_pool = bool(prop.get("has_pool", False))
    sea_view = bool(prop.get("sea_view", False))
    if not has_pool and not sea_view:
        reasons.append("אין בריכה ואין נוף לים (נדרש לפחות אחד)")

    is_ideal = len(reasons) == 0
    return is_ideal, reasons

# ==========================================
# פונקציות חישוב פיננסיות לנכס
# ==========================================
def calculate_financials(prop):
    price = float(prop.get("price_eur", 0) or 0)
    built_sqm = float(prop.get("built_sqm", 0) or 0)
    physical_score = float(prop.get("physical_score", 5.0) or 5.0)
    airbnb_score = float(prop.get("airbnb_score", 5.0) or 5.0)
    
    closing_costs = price * 0.0819
    renovation_costs = 15000 + max(0, (10 - physical_score)) * 10000
    total_investment = price + closing_costs + renovation_costs
    
    enfia = (built_sqm if built_sqm > 0 else 100.0) * 3.0
    maintenance_and_insurance = 1200.0
    annual_fixed_expenses = enfia + maintenance_and_insurance
    
    estimated_nights = int(airbnb_score * 12)
    nightly_rate = 350.0
    gross_annual_revenue = estimated_nights * nightly_rate
    
    mgmt_fee = gross_annual_revenue * 0.20
    income_tax = gross_annual_revenue * 0.15
    net_revenue_after_mgmt_tax = gross_annual_revenue - mgmt_fee - income_tax
    
    net_annual_profit = net_revenue_after_mgmt_tax - annual_fixed_expenses
    net_roi = (net_annual_profit / total_investment * 100) if total_investment > 0 else 0
    
    return {
        "closing_costs": round(closing_costs),
        "renovation_costs": round(renovation_costs),
        "total_investment": round(total_investment),
        "annual_fixed_expenses": round(annual_fixed_expenses),
        "gross_annual_revenue": round(gross_annual_revenue),
        "net_annual_profit": round(net_annual_profit),
        "net_roi": round(net_roi, 2)
    }

# ==========================================
# פונקציית חילוץ מקומית חכמה ומדויקת ב-Python
# ==========================================
def parse_text_locally(text, url=""):
    combined = f"{text} {url}".strip()
    
    data = {
        "property_title": "נכס באפוקורונס",
        "region": "כרתים",
        "city_town": "חאניה",
        "village": "אפוקורונס",
        "price_eur": 250000,
        "built_sqm": 0,
        "plot_sqm": 0,
        "bedrooms": 2,
        "bathrooms": 2,
        "has_pool": False,
        "sea_view": False,
        "physical_score": 7.5,
        "location_score": 7.5,
        "airbnb_score": 7.5,
        "summary": text[:300] if text else "נכס מהזנה ידנית"
    }
    
    if not combined:
        return data

    village_scores = {
        "kokkino chorio": ("קוקינו חוריו", 9.0),
        "kokkino": ("קוקינו חוריו", 9.0),
        "plaka": ("פלאקה", 9.0),
        "almyrida": ("אלמירידה", 9.0),
        "kefalas": ("קפלאס", 8.5),
        "vamos": ("ואמוס", 8.5),
        "gavalochori": ("גובאלוכורי", 8.5),
        "kalyves": ("קליבס", 8.5),
        "georgioupoli": ("גאורגיופוליס", 8.0),
        "drapanos": ("דראפנוס", 8.0)
    }
    
    found_village = False
    for en_v, (he_v, loc_score) in village_scores.items():
        if en_v in combined.lower():
            data["village"] = he_v
            data["property_title"] = f"בית/וילה ב{he_v}"
            data["location_score"] = loc_score
            found_village = True
            break
            
    if not found_village:
        data["village"] = "אפוקורונס"
        data["location_score"] = 7.5

    price_match = re.search(r'(?:€|EUR|\$)\s*([\d,]+)|([\d,]+)\s*(?:€|EUR|euros)', combined, re.IGNORECASE)
    if price_match:
        val = price_match.group(1) or price_match.group(2)
        try:
            parsed_price = int(val.replace(',', ''))
            if parsed_price > 10000:
                data["price_eur"] = parsed_price
        except:
            pass

    bed_match = re.search(r'(\d+)\s*(?:-|\s)*(?:bed|bedroom|bedrooms|חדרי שינה|חדרים)', combined, re.IGNORECASE)
    if bed_match:
        try:
            data["bedrooms"] = int(bed_match.group(1))
        except:
            pass

    bath_match = re.search(r'(\d+)\s*(?:-|\s)*(?:bath|bathroom|bathrooms|חדרי רחצה)', combined, re.IGNORECASE)
    if bath_match:
        try:
            data["bathrooms"] = int(bath_match.group(1))
        except:
            pass

    built_match = re.search(r'(\d+)\s*(?:sqm|sq\.m|m2|מ"ר|מטר בנוי)', combined, re.IGNORECASE)
    if built_match:
        try:
            data["built_sqm"] = int(built_match.group(1))
        except:
            pass

    plot_match = re.search(r'(?:plot|land|garden|lot)\s*(?:of)?\s*(\d+)|(\d+)\s*(?:sqm|m2)\s*(?:plot|land|garden|lot)', combined, re.IGNORECASE)
    if plot_match:
        try:
            val = plot_match.group(1) or plot_match.group(2)
            data["plot_sqm"] = int(val)
        except:
            pass
    else:
        data["plot_sqm"] = 0

    if re.search(r'pool|בריכה|swimming', combined, re.IGNORECASE):
        data["has_pool"] = True
    if re.search(r'sea\s*view|sea\s*views|נוף\s*לים|panoramic\s*view', combined, re.IGNORECASE):
        data["sea_view"] = True

    phys_score = 7.0
    airbnb_score = 7.0

    if data["has_pool"]:
        phys_score += 1.0
        airbnb_score += 1.0
    if data["sea_view"]:
        phys_score += 1.0
        airbnb_score += 1.0
    if data["bathrooms"] >= 2:
        phys_score += 0.5

    data["physical_score"] = min(10.0, phys_score)
    data["airbnb_score"] = min(10.0, airbnb_score)

    return data

# ==========================================
# 2. מנוע AI עם מנגנון Fallback מרובה מודלים
# ==========================================
SYSTEM_INSTRUCTION = """
אתה מומחה נדל"ן ומעריך נכסים ביוון. תפקידך לחלץ מודעת נדל"ן (מטקסט באנגלית/עברית, קישור או תמונות/צילומי מסך מרובים) ולהחזיר אך ורק אובייקט JSON תקני ללא שום דיבורים נוספים.
אם מועלות מספר תמונות או טקסט באנגלית, תרגם וחלץ את המידע לכדי ניתוח בעברית.

השדות ב-JSON חייבים להיות:
{
  "property_title": "כותרת קצרה",
  "region": "אזור/אי (למשל כרתים)",
  "city_town": "עיר/מחוז (למשל חאניה)",
  "village": "כפר/שכונה",
  "price_eur": 0,
  "built_sqm": 0,
  "plot_sqm": 0,
  "bedrooms": 0,
  "bathrooms": 0,
  "has_pool": false,
  "sea_view": false,
  "physical_score": 5.0,
  "location_score": 5.0,
  "airbnb_score": 5.0,
  "summary": "תקציר קצר בעברית"
}
אם נתון מסוים חסר, שער באופן הגיוני או שים 0/false.
"""

def analyze_with_gemini_with_fallback(user_text=None, image_files=None):
    models_to_try = [
        "gemini-3.8-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash"
    ]
    
    contents = []
    if image_files:
        for img_file in image_files:
            if img_file is not None:
                contents.append(Image.open(img_file))
            
    if user_text:
        contents.append(user_text)
        
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_INSTRUCTION,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(contents)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            return json.loads(raw_text)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            else:
                continue

    return None

# ==========================================
# 3. ממשק המשתמש (UI) והטענת נתונים
# ==========================================
st.title("🏠 מנוע השוואת נכסים ביוון - לוח משפחתי")
st.caption("הוסיפו צילומי מסך או טקסט של מודעה, וה-AI יחלץ את הנתונים, ידרג אותה ויחשב את התשואה והעלויות הנילוות.")

st.session_state.properties = load_data()

with st.expander("🎯 קריטריוני הנכס האידאלי לרשימת המיקוד (לחץ לצפייה)", expanded=False):
    st.markdown("""
    * **📍 מיקום:** כל כפרי מחוז **אפוקורונס** (Apokoronas).
    * **🛏️ חדרי שינה:** מינימום **3 חדרי שינה**.
    * **📐 שטח בנוי:** מינימום **80 מ"ר**.
    * **🛠️ מצב הנכס:** מוכן לכניסה / ללא צורך בשיפוץ (ציון פיזי $\ge 7.0$).
    * **🌳 שטח חצר:** מינימום **200 מ"ר** (נכס ללא נתון חצר מפורש במודעה ייכנס גם הוא!).
    * **🏊‍♂️ בריכה / 🌊 נוף לים:** **לפחות אחד מהם נדרש!**
      * **אם יש בריכה:** תוספת של **+1.0 נקודה** לציון.
      * **אם יש נוף לים:** תוספת של **+1.0 נקודה** לציון.
    """)

with st.expander("➕ הוספת נכס חדש (אוטומטי או ידני)", expanded=True):
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        added_by = st.selectbox("שם בן המשפחה המוסיף:", ["דודי", "גל", "מאיר/פזית", "אחר"])
        property_url = st.text_input("🔗 קישור למודעה / פוסט (לשמירה וחזרה ישירה לנכס):")
        property_text = st.text_area("טקסט המודעה (בעברית או באנגלית):", placeholder="הדבק כאן את טקסט המודעה...")
        
    with col_input2:
        uploaded_images = st.file_uploader(
            "📷 צילומי מסך של המודעה (ניתן להדביק ב-Ctrl+V או לבחור קבצים):", 
            type=["jpg", "jpeg", "png"], 
            accept_multiple_files=True,
            key="multi_img_uploader"
        )
        if uploaded_images:
            st.caption(f"נבחרו {len(uploaded_images)} תמונות לניתוח:")
            cols = st.columns(min(len(uploaded_images), 4))
            for idx, img in enumerate(uploaded_images):
                with cols[idx % 4]:
                    st.image(img, use_container_width=True)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_auto = st.button("🚀 נתח והוסף אוטומטית ללוח", use_container_width=True)
    with col_btn2:
        btn_manual_toggle = st.button("✏️ פתח טופס הזנה/עריכה ידנית", use_container_width=True)

    if btn_auto:
        st.session_state["m_extracted"] = None

        if not property_text and not uploaded_images and not property_url:
            st.error("יש לספק לפחות צילום מסך אחד, טקסט או קישור למודעה.")
        else:
            with st.spinner("מנוע ה-AI מנתח את הנתונים ושומר באופן קבוע..."):
                parsed_data = analyze_with_gemini_with_fallback(user_text=property_text, image_files=uploaded_images)
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                if parsed_data is not None:
                    current_props = load_data()
                    parsed_data["id"] = len(current_props) + 1 if current_props else 1
                    parsed_data["added_by"] = added_by
                    parsed_data["created_at"] = today_str
                    parsed_data["url"] = property_url.strip() if property_url and property_url.strip() != "" else "N/A"
                    
                    current_props.append(parsed_data)
                    save_data(current_props)
                    
                    st.session_state.properties = current_props
                    st.success(f"הנכס '{parsed_data.get('property_title', 'נכס חדש')}' נשמר בהצלחה באופן קבוע!")
                    st.rerun()
                else:
                    st.session_state["m_extracted"] = parse_text_locally(property_text, property_url)
                    st.session_state["show_manual_add"] = True
                    st.warning("⚠️ המכסה החינמית ב-API בשיא. הטופס הידני למטה נפתח עם הנתונים המדויקים שחולצו מהטקסט!")

    if btn_manual_toggle:
        st.session_state["m_extracted"] = parse_text_locally(property_text, property_url)
        st.session_state["show_manual_add"] = True

# ==========================================
# 3.1 טופס הזנה ידנית חכם ומדויק
# ==========================================
if st.session_state.get("show_manual_add", False):
    st.divider()
    st.info("📝 **טופס הזנת נכס ידנית / חצי-אוטומטית:**")
    
    if st.button("🪄 חלץ ומלא שדות מהטקסט/התמונות למעלה"):
        with st.spinner("מחלץ נתונים לשדות הטופס..."):
            extracted = analyze_with_gemini_with_fallback(user_text=property_text, image_files=uploaded_images)
            if not extracted:
                extracted = parse_text_locally(property_text, property_url)
                st.warning("⚠️ ה-API של Gemini בעומס. השדות אוכלסו באמצעות חילוץ הטקסט המקומי!")
            else:
                st.success("הנתונים חולצו בהצלחה באמצעות AI!")
            st.session_state["m_extracted"] = extracted

    ext = st.session_state.get("m_extracted")
    if not ext:
        ext = parse_text_locally(property_text, property_url)

    today_default = datetime.now().strftime("%Y-%m-%d")

    with st.form(key="manual_add_form"):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            m_title = st.text_input("כותרת/שם הנכס:", value=ext.get("property_title", "נכס באפוקורונס"))
            m_url = st.text_input("🔗 קישור למודעה / פוסט:", value=property_url if property_url else ext.get("url", "N/A"))
            m_price = st.number_input("מחיר ב-€:", value=int(ext.get("price_eur", 250000) or 250000), step=5000)
            m_built = st.number_input("שטח בנוי (מ\"ר):", value=int(ext.get("built_sqm", 0) or 0), step=5)
            m_plot = st.number_input("שטח מגרש (מ\"ר):", value=int(ext.get("plot_sqm", 0) or 0), step=10)
        with mc2:
            m_region = st.text_input("אזור/אי:", value=ext.get("region", "כרתים"))
            m_city = st.text_input("עיר/מחוז:", value=ext.get("city_town", "חאניה"))
            m_village = st.text_input("כפר/שכונה:", value=ext.get("village", "אפוקורונס"))
            m_bedrooms = st.number_input("חדרי שינה:", value=int(ext.get("bedrooms", 2) or 2), min_value=0)
            m_bathrooms = st.number_input("חדרי רחצה:", value=int(ext.get("bathrooms", 2) or 2), min_value=0)
            m_created_at = st.text_input("📅 תאריך הכנסת המודעה (YYYY-MM-DD):", value=ext.get("created_at", today_default))
        with mc3:
            m_has_pool = st.checkbox("🏊‍♂️ בריכה פרטית", value=bool(ext.get("has_pool", False)))
            m_sea_view = st.checkbox("🌊 נוף לים", value=bool(ext.get("sea_view", True)))
            m_phys = st.slider("ציון מצב פיזי (1-10):", 1.0, 10.0, float(ext.get("physical_score", 8.5) or 8.5), 0.5)
            m_loc = st.slider("ציון מיקום (1-10):", 1.0, 10.0, float(ext.get("location_score", 9.0) or 9.0), 0.5)
            m_airbnb = st.slider("ציון פוטנציאל Airbnb (1-10):", 1.0, 10.0, float(ext.get("airbnb_score", 9.0) or 9.0), 0.5)

        m_summary = st.text_area("תקציר/הערות נוספות:", value=ext.get("summary", property_text[:300] if property_text else "נכס שמור מהזנה ידנית."))
        submit_manual = st.form_submit_button("💾 שמור נכס בלוח המשפחתי")

        if submit_manual:
            manual_prop = {
                "property_title": m_title,
                "region": m_region,
                "city_town": m_city,
                "village": m_village,
                "price_eur": m_price,
                "built_sqm": m_built,
                "plot_sqm": m_plot,
                "bedrooms": m_bedrooms,
                "bathrooms": m_bathrooms,
                "has_pool": m_has_pool,
                "sea_view": m_sea_view,
                "physical_score": m_phys,
                "location_score": m_loc,
                "airbnb_score": m_airbnb,
                "summary": m_summary,
                "added_by": added_by,
                "created_at": m_created_at.strip(),
                "url": m_url.strip() if m_url and m_url.strip() != "" else "N/A"
            }
            
            current_props = load_data()
            manual_prop["id"] = len(current_props) + 1 if current_props else 1
            current_props.append(manual_prop)
            save_data(current_props)
            
            st.session_state.properties = current_props
            st.session_state["show_manual_add"] = False
            if "m_extracted" in st.session_state:
                del st.session_state["m_extracted"]
            st.success("הנכס נשמר בהצלחה בלוח!")
            st.rerun()

st.divider()

# ==========================================
# 4. הצגת טבלת ההשוואה, עריכה ומחיקה
# ==========================================
if not st.session_state.properties:
    st.info("עדיין לא הוספו נכסים. השתמשו בטופס למעלה כדי להוסיף את הנכס הראשון!")
else:
    enriched_props = []
    for p in st.session_state.properties:
        is_ideal, reasons = evaluate_ideal_criteria(p)
        
        phys = float(p.get("physical_score", 5.0) or 5.0)
        loc = float(p.get("location_score", 5.0) or 5.0)
        airbnb = float(p.get("airbnb_score", 5.0) or 5.0)
        
        if bool(p.get("has_pool", False)):
            phys = min(10.0, phys + 1.0)
            airbnb = min(10.0, airbnb + 1.0)
        if bool(p.get("sea_view", False)):
            loc = min(10.0, loc + 1.0)
            airbnb = min(10.0, airbnb + 1.0)
            
        base_score = (0.4 * phys) + (0.3 * loc) + (0.3 * airbnb)
        final_score = round(base_score if is_ideal else max(1.0, base_score - 2.0), 1)
        
        p["is_ideal"] = is_ideal
        p["unmet_reasons"] = reasons
        p["total_score"] = final_score
        
        fin = calculate_financials(p)
        merged = {**p, **fin}
        enriched_props.append(merged)

    df_all = pd.DataFrame(enriched_props)
    
    df_target = df_all[df_all["is_ideal"] == True].sort_values(by="total_score", ascending=False)
    df_secondary = df_all[df_all["is_ideal"] == False].sort_values(by="total_score", ascending=False)

    excel_file = "greece_properties_comparison.xlsx"
    df_all.to_excel(excel_file, index=False)
    with open(excel_file, "rb") as f:
        st.download_button(
            label="📥 הורד טבלה מעודכנת לקובץ Excel (כולל סיווג, תאריכים וחישובי תשואה)",
            data=f,
            file_name="Greece_Properties_Comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def render_property_card(row, is_target=True):
        fin = calculate_financials(row)
        prop_id = row.get("id")
        created_date = row.get("created_at", "N/A")
        
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2.5, 2.5, 1.2])
            
            with col1:
                badge = "🎯 **נכס מיקוד אידאלי**" if is_target else "⚠️ **נכס בעדיפות משנית**"
                st.markdown(f"### **{row.get('property_title', 'נכס')}**")
                st.caption(badge)
                st.write(f"📍 **מיקום:** {row.get('region', '')}, {row.get('city_town', '')} ({row.get('village', '')})")
                st.write(f"📝 **תקציר:** {row.get('summary', '')}")
                if not is_target and row.get('unmet_reasons'):
                    st.warning("❌ **סיבות לחוסר התאמה:** " + ", ".join(row.get('unmet_reasons')))
                st.write(f"👤 **התווסף ע\"י:** {row.get('added_by', '')} | 📅 **בתאריך:** {created_date}")
                
            with col2:
                price = row.get('price_eur', 0)
                st.write(f"💰 **מחיר נכס:** €{price:,}" if isinstance(price, (int, float)) else f"💰 **מחיר:** €{price}")
                st.write(f"📐 **שטח בנוי:** {row.get('built_sqm', 0)} מ\"ר | **מגרש:** {row.get('plot_sqm', 0)} מ\"ר")
                st.write(f"🛏️ **חדרים:** {row.get('bedrooms', 0)} חדרים | 🛁 {row.get('bathrooms', 0)} רחצה")
                st.write(f"🏊‍♂️ **בריכה:** {'כן' if row.get('has_pool') else 'לא'} | 🌊 **נוף לים:** {'כן' if row.get('sea_view') else 'לא'}")
                
            with col3:
                st.markdown("💰 **ניתוח השקעה ותשואה מוערכת:**")
                st.write(f"🏷️ **הוצאות רכישה (8.19%):** €{fin['closing_costs']:,}")
                st.write(f"🛠️ **שיפוץ, שדרוג וריהוט:** €{fin['renovation_costs']:,}")
                st.write(f"💵 **סך הכל השקעה נדרשת:** **€{fin['total_investment']:,}**")
                st.write(f"📈 **תשואה נטו משוערת:** **{fin['net_roi']}% לשנה**")
                st.caption(f"רווח נטו משוער: €{fin['net_annual_profit']:,} / שנה")

            with col4:
                st.metric("🏆 ציון", f"{row.get('total_score', 0)}/10")
                st.caption(f"פיזי: {row.get('physical_score', 0)} | מיקום: {row.get('location_score', 0)} | Airbnb: {row.get('airbnb_score', 0)}")
                
                url_val = str(row.get('url', 'N/A'))
                if url_val != "N/A" and url_val.startswith("http"):
                    st.markdown(f"[🔗 מודעה מקורית]({url_val})")
                
                st.write("")
                if st.button("🗑️ מחק", key=f"del_{prop_id}"):
                    updated_props = [p for p in st.session_state.properties if p.get("id") != prop_id]
                    save_data(updated_props)
                    st.session_state.properties = updated_props
                    st.warning("הנכס נמחק.")
                    st.rerun()

            with st.expander(f"✏️ ערוך/עדכן נתונים (כולל תאריך) עבור נכס #{prop_id}"):
                with st.form(key=f"edit_form_{prop_id}"):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        e_title = st.text_input("כותרת הנכס:", value=str(row.get('property_title', '')))
                        e_price = st.number_input("מחיר ב-€:", value=int(row.get('price_eur', 0) or 0))
                        e_built = st.number_input("שטח בנוי (מ\"ר):", value=int(row.get('built_sqm', 0) or 0))
                        e_plot = st.number_input("שטח מגרש (מ\"ר):", value=int(row.get('plot_sqm', 0) or 0))
                    with ec2:
                        e_region = st.text_input("אזור/אי:", value=str(row.get('region', '')))
                        e_city = st.text_input("עיר/מחוז:", value=str(row.get('city_town', '')))
                        e_village = st.text_input("כפר/שכונה:", value=str(row.get('village', '')))
                        e_bedrooms = st.number_input("חדרי שינה:", value=int(row.get('bedrooms', 0) or 0), min_value=0)
                        e_bathrooms = st.number_input("חדרי רחצה:", value=int(row.get('bathrooms', 0) or 0), min_value=0)
                        e_created_at = st.text_input("📅 תאריך הכנסת המודעה (YYYY-MM-DD):", value=str(row.get('created_at', created_date)))
                    with ec3:
                        e_sea_view = st.checkbox("🌊 נוף לים", value=bool(row.get('sea_view', False)))
                        e_has_pool = st.checkbox("🏊‍♂️ בריכה", value=bool(row.get('has_pool', False)))
                        e_phys = st.slider("ציון פיזי (1-10):", 1.0, 10.0, float(row.get('physical_score', 5.0) or 5.0), 0.1)
                        e_loc = st.slider("ציון מיקום (1-10):", 1.0, 10.0, float(row.get('location_score', 5.0) or 5.0), 0.1)
                        e_airbnb = st.slider("ציון Airbnb (1-10):", 1.0, 10.0, float(row.get('airbnb_score', 5.0) or 5.0), 0.1)

                    e_summary = st.text_area("תקציר/הערות נוספות:", value=str(row.get('summary', '')))

                    submit_edit = st.form_submit_button("💾 שמור שינויים ועדכן נכס")
                    
                    if submit_edit:
                        all_props = load_data()
                        for p in all_props:
                            if p.get("id") == prop_id:
                                p["property_title"] = e_title
                                p["price_eur"] = e_price
                                p["built_sqm"] = e_built
                                p["plot_sqm"] = e_plot
                                p["region"] = e_region
                                p["city_town"] = e_city
                                p["village"] = e_village
                                p["bedrooms"] = e_bedrooms
                                p["bathrooms"] = e_bathrooms
                                p["created_at"] = e_created_at.strip()
                                p["sea_view"] = e_sea_view
                                p["has_pool"] = e_has_pool
                                p["physical_score"] = round(e_phys, 1)
                                p["location_score"] = round(e_loc, 1)
                                p["airbnb_score"] = round(e_airbnb, 1)
                                p["summary"] = e_summary
                                break
                        
                        save_data(all_props)
                        st.session_state.properties = all_props
                        st.success("הנכס עודכן והתאריך נשמר!")
                        st.rerun()

    # --- הצגת רשימת המיקוד ---
    st.markdown("## 🎯 רשימת מיקוד - נכסים אידאליים")
    if df_target.empty:
        st.warning("כעת אין נכסים בלוח שעונים על קריטריוני המיקוד. בדקו את הרשימה המשנית למטה.")
    else:
        for idx, row in df_target.iterrows():
            render_property_card(row, is_target=True)

    st.divider()

    # --- הצגת נכסים בעלי עניין ---
    st.markdown("## ⚠️ נכסים בעלי עניין (עדיפות משנית / חוסר התאמה לקריטריון)")
    if df_secondary.empty:
        st.info("כל הנכסים בלוח עונים על קריטריוני המיקוד!")
    else:
        for idx, row in df_secondary.iterrows():
            render_property_card(row, is_target=False)
