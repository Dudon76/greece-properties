import os
import json
import base64
import requests
import streamlit as st
import pandas as pd
from PIL import Image
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
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "") # למשל: Dudon76/greece-properties
FILE_PATH = "properties_data.json"

# ==========================================
# מנגנון שמירה קבוע ב-GitHub (אמינות 100%)
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

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    res = requests.get(url, headers=get_github_headers())
    if res.status_code == 200:
        content = res.json()
        file_data = base64.b64decode(content["content"]).decode("utf-8")
        st.session_state["file_sha"] = content["sha"]
        return json.loads(file_data)
    else:
        return []

def save_data(data_list):
    st.session_state.local_db = data_list
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    json_bytes = json.dumps(data_list, ensure_ascii=False, indent=2).encode("utf-8")
    base64_content = base64.b64encode(json_bytes).decode("utf-8")

    payload = {
        "message": "Update properties database",
        "content": base64_content
    }
    if "file_sha" in st.session_state:
        payload["sha"] = st.session_state["file_sha"]

    res = requests.put(url, json=payload, headers=get_github_headers())
    if res.status_code in [200, 201]:
        st.session_state["file_sha"] = res.json()["content"]["sha"]
    else:
        st.error(f"שגיאה בשמירה ל-GitHub: {res.json().get('message')}")

# ==========================================
# פונקציות חישוב פיננסיות לנכס
# ==========================================
def calculate_financials(prop):
    price = float(prop.get("price_eur", 0) or 0)
    built_sqm = float(prop.get("built_sqm", 0) or 0)
    physical_score = float(prop.get("physical_score", 5.0) or 5.0)
    airbnb_score = float(prop.get("airbnb_score", 5.0) or 5.0)
    
    # הוצאות רכישה נלוות (8.19% מס רכישה, טאבו, עו"ד, נוטריון, חברת ליווי)
    closing_costs = price * 0.0819
    
    # עלויות שיפוץ, שדרוג וריהוט (15,000 קבוע + 10,000 לכל נקודה חסרה בציון פיזי)
    renovation_costs = 15000 + max(0, (10 - physical_score)) * 10000
    
    # סך ההשקעה הנדרשת
    total_investment = price + closing_costs + renovation_costs
    
    # הוצאות תפעול קבועות (אנפיה + תחזוקה + ביטוח)
    enfia = built_sqm * 3.0
    maintenance_and_insurance = 1200.0  # גנן, בריכה, ביטוח
    annual_fixed_expenses = enfia + maintenance_and_insurance
    
    # הערכת הכנסה מ-Airbnb (לפי ציון Airbnb ולילות תפוסה)
    estimated_nights = int(airbnb_score * 12)  # למשל: ציון 8 = 96 לילות בשנה
    nightly_rate = 350.0  # מחיר ממוצע ללילה
    gross_annual_revenue = estimated_nights * nightly_rate
    
    # ניכוי ניהול (20%) ומיסים (15%)
    mgmt_fee = gross_annual_revenue * 0.20
    income_tax = gross_annual_revenue * 0.15
    net_revenue_after_mgmt_tax = gross_annual_revenue - mgmt_fee - income_tax
    
    # רווח נטו קופתי
    net_annual_profit = net_revenue_after_mgmt_tax - annual_fixed_expenses
    
    # תשואה נטו %
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

if "properties" not in st.session_state:
    st.session_state.properties = load_data()

# ==========================================
# 2. מנוע AI לחילוץ נתונים מ-Gemini
# ==========================================
SYSTEM_INSTRUCTION = """
אתה מומחה נדל"ן ומעריך נכסים ביוון. תפקידך לחלץ מודעת נדל"ן (מטקסט, קישור או תמונות/צילומי מסך) ולהחזיר אך ורק אובייקט JSON תקני ללא טקסט מעבר לכך.
אם מועלות שתי תמונות, חבר את המידע מכל התמונות יחד לכדי ניתוח של נכס אחד.

השדות ב-JSON חייבים להיות:
{
  "property_title": "כותרת קצרה",
  "region": "אזור/אי (למשל כרתים)",
  "city_town": "עיר/מחוז",
  "village": "כפר/שכונה",
  "price_eur": 0,
  "built_sqm": 0,
  "plot_sqm": 0,
  "bedrooms": 0,
  "bathrooms": 0,
  "has_pool": false,
  "sea_view": false,
  "physical_score": 0.0,
  "location_score": 0.0,
  "airbnb_score": 0.0,
  "total_score": 0.0,
  "summary": "תקציר קצר בעברית"
}
חוקי ניקוד (1-10):
total_score = (0.4 * physical_score) + (0.3 * location_score) + (0.3 * airbnb_score)
"""

def analyze_with_gemini(user_text=None, image_files=None):
    model = genai.GenerativeModel(
        model_name="gemini-3.8-flash",
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config={"response_mime_type": "application/json"}
    )
    
    contents = []
    if image_files:
        for img_file in image_files:
            if img_file is not None:
                contents.append(Image.open(img_file))
            
    if user_text:
        contents.append(user_text)
        
    response = model.generate_content(contents)
    return json.loads(response.text)

# ==========================================
# 3. ממשק המשתמש (UI)
# ==========================================
st.title("🏠 מנוע השוואת נכסים ביוון - לוח משפחתי")
st.caption("הוסיפו צילומי מסך או טקסט של מודעה, וה-AI יחלץ את הנתונים, ידרג אותה ויחשב את התשואה והעלויות הנילוות.")

with st.expander("➕ הוספת נכס חדש (לחץ להרחבה)", expanded=True):
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        added_by = st.selectbox("שם בן המשפחה המוסיף:", ["דודי", "גל", "מאיר/פזית", "אחר"])
        property_url = st.text_input("🔗 קישור למודעה / פוסט (לשמירה וחזרה ישירה לנכס):")
        property_text = st.text_area("טקסט המודעה / הערות נוספות:", placeholder="הדבק כאן טקסט במידת הצורך...")
        
    with col_input2:
        uploaded_image_1 = st.file_uploader("📷 צילום מסך 1 (חלק ראשי):", type=["jpg", "jpeg", "png"], key="img1_uploader")
        if uploaded_image_1 is not None:
            st.image(uploaded_image_1, caption=f"תמונה 1: {uploaded_image_1.name}", width=200)
            
        st.write("---")
        
        uploaded_image_2 = st.file_uploader("📷 צילום מסך 2 (המשך המודעה - אופציונלי):", type=["jpg", "jpeg", "png"], key="img2_uploader")
        if uploaded_image_2 is not None:
            st.image(uploaded_image_2, caption=f"תמונה 2: {uploaded_image_2.name}", width=200)
        
    images_to_process = [img for img in [uploaded_image_1, uploaded_image_2] if img is not None]

    if st.button("🚀 נתח והוסף נכס ללוח", use_container_width=True):
        if not property_text and not images_to_process and not property_url:
            st.error("יש לספק לפחות צילום מסך אחד, טקסט או קישור למודעה.")
        else:
            with st.spinner("מנוע ה-AI מנתח את הנתונים ושומר באופן קבוע..."):
                try:
                    parsed_data = analyze_with_gemini(user_text=property_text, image_files=images_to_process)
                    
                    current_props = load_data()
                    parsed_data["id"] = len(current_props) + 1
                    parsed_data["added_by"] = added_by
                    parsed_data["url"] = property_url.strip() if property_url and property_url.strip() != "" else "N/A"
                    
                    current_props.append(parsed_data)
                    save_data(current_props)
                    
                    st.session_state.properties = current_props
                    st.success(f"הנכס '{parsed_data['property_title']}' נשמר בהצלחה באופן קבוע!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בניתוח המודעה: {e}")

st.divider()

# ==========================================
# 4. הצגת טבלת ההשוואה והמחיקה
# ==========================================
st.subheader("📋 טבלת השוואת נכסים (כולל ניתוח תשואה והשקעה נדרשת)")

st.session_state.properties = load_data()

if not st.session_state.properties:
    st.info("עדיין לא הוספו נכסים. השתמשו בטופס למעלה כדי להוסיף את הנכס הראשון!")
else:
    # חישוב הנתונים הפיננסיים לכל נכס בטבלה
    enriched_props = []
    for p in st.session_state.properties:
        fin = calculate_financials(p)
        merged = {**p, **fin}
        enriched_props.append(merged)

    df = pd.DataFrame(enriched_props)
    if "total_score" in df.columns:
        df = df.sort_values(by="total_score", ascending=False)
    
    excel_file = "greece_properties_comparison.xlsx"
    df.to_excel(excel_file, index=False)
    with open(excel_file, "rb") as f:
        st.download_button(
            label="📥 הורד טבלה מעודכנת לקובץ Excel (כולל חישובי תשואה ועלויות)",
            data=f,
            file_name="Greece_Properties_Comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    for idx, row in df.iterrows():
        fin = calculate_financials(row)
        
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2.5, 2.5, 1])
            
            with col1:
                st.markdown(f"### **{row.get('property_title', 'נכס')}**")
                st.write(f"📍 **מיקום:** {row.get('region', '')}, {row.get('city_town', '')} ({row.get('village', '')})")
                st.write(f"📝 **תקציר:** {row.get('summary', '')}")
                st.write(f"👤 **התווסף ע\"י:** {row.get('added_by', '')}")
                
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
                url_val = str(row.get('url', 'N/A'))
                if url_val != "N/A" and url_val.startswith("http"):
                    st.markdown(f"[🔗 מודעה מקורית]({url_val})")
                
                st.write("")
                if st.button("🗑️ מחק", key=f"del_{row.get('id', idx)}"):
                    updated_props = [p for p in st.session_state.properties if p.get("id") != row.get("id")]
                    save_data(updated_props)
                    st.session_state.properties = updated_props
                    st.warning("הנכס נמחק.")
                    st.rerun()
