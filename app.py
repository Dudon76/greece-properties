import os
import json
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

# שליפת מפתח ה-API מתוך ה-Secrets של Streamlit
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# קובץ הנתונים המקומי (שומר את הנתונים בזמן אמת)
DB_FILE = "properties_db.json"

# ==========================================
# 2. ניהול בסיס הנתונים (מחיקה, שמירה, טעינה)
# ==========================================
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if "properties" not in st.session_state:
    st.session_state.properties = load_data()

# ==========================================
# 3. מנוע AI לחילוץ נתונים מ-Gemini
# ==========================================
SYSTEM_INSTRUCTION = """
אתה מומחה נדל"ן ומעריך נכסים ביוון. תפקידך לחלץ מודעת נדל"ן (מטקסט, קישור או תמונות/צילומי מסך) ולהחזיר אך ורק אובייקט JSON תקני ללא טקסט מעבר לכך.
אם מועלות כמה תמונות, חבר את המידע מכל התמונות יחד לכדי ניתוח של נכס אחד.

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
    
    # במידה והועלו תמונות (אחת או יותר)
    if image_files:
        for img_file in image_files:
            img = Image.open(img_file)
            contents.append(img)
            
    if user_text:
        contents.append(user_text)
        
    response = model.generate_content(contents)
    return json.loads(response.text)

# ==========================================
# 4. ממשק המשתמש (UI)
# ==========================================
st.title("🏠 מנוע השוואת נכסים ביוון - לוח משפחתי")
st.caption("הוסיפו קישור או צילום מסך של מודעה, וה-AI יחלץ את הנתונים וידרג אותה אוטומטית.")

# --- אזור הוספת נכס חדש ---
with st.expander("➕ הוספת נכס חדש (לחץ להרחבה)", expanded=True):
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        added_by = st.selectbox("שם בן המשפחה המוסיף:", ["דודי", "גל", "מאיר/פזית", "אחר"])
        property_url = st.text_input("קישור למודעה / פוסט (אופציונלי):")
        property_text = st.text_area("טקסט המודעה / הערות נוספות:")
        
    with col_input2:
        # תמיכה בהעלאת מרובת קבצים (Multiple Upload)
        uploaded_images = st.file_uploader(
            "העלה צילומי מסך של המודעה (ניתן לבחור מספר תמונות):", 
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True
        )
        
        # חיווי ויזואלי להעלאת קבצים
        if uploaded_images:
            st.success(f"📸 הועלו {len(uploaded_images)} תמונות בהצלחה!")
            for img in uploaded_images:
                st.caption(f"✔️ {img.name}")
        
    if st.button("🚀 נתח והוסף נכס ללוח", use_container_width=True):
        if not property_text and not uploaded_images and not property_url:
            st.error("יש לספק לפחות תמונה, טקסט או קישור למודעה.")
        else:
            with st.spinner("מנוע ה-AI מנתח את כל התמונות והנתונים ומחשב ניקוד..."):
                try:
                    combined_text = f"URL: {property_url}\n{property_text}" if property_url else property_text
                    parsed_data = analyze_with_gemini(user_text=combined_text, image_files=uploaded_images)
                    
                    # הוספת מזהה ייחודי ושם המוסיף
                    parsed_data["id"] = len(st.session_state.properties) + 1
                    parsed_data["added_by"] = added_by
                    parsed_data["url"] = property_url if property_url else "N/A"
                    
                    st.session_state.properties.append(parsed_data)
                    save_data(st.session_state.properties)
                    st.success(f"הנכס '{parsed_data['property_title']}' נוסף בהצלחה!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בניתוח המודעה: {e}")

st.divider()

# ==========================================
# 5. הצגת טבלת ההשוואה והמחיקה
# ==========================================
st.subheader("📋 טבלת השוואת נכסים (ממוינת לפי ציון משוקלל)")

if not st.session_state.properties:
    st.info("עדיין לא הוספו נכסים. השתמשו בטופס למעלה כדי להוסיף את הנכס הראשון!")
else:
    # המרת הנתונים ל-DataFrame של Pandas
    df = pd.DataFrame(st.session_state.properties)
    
    # מיון לפי ציון משוקלל יורד
    df = df.sort_values(by="total_score", ascending=False)
    
    # כפתור ייצוא לאקסל
    excel_file = "greece_properties_comparison.xlsx"
    df.to_excel(excel_file, index=False)
    with open(excel_file, "rb") as f:
        st.download_button(
            label="📥 הורד טבלה מעודכנת לקובץ Excel",
            data=f,
            file_name="Greece_Properties_Comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    # תצוגת הכרטיסיות/שורות בטבלה
    for idx, row in df.iterrows():
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"### **{row['property_title']}**")
                st.write(f"📍 **מיקום:** {row['region']}, {row['city_town']} ({row['village']})")
                st.write(f"📝 **תקציר:** {row['summary']}")
                st.write(f"👤 **התווסף ע\"י:** {row['added_by']}")
                
            with col2:
                st.write(f"💰 **מחיר:** €{row['price_eur']:,}")
                st.write(f"📐 **שטח בנוי:** {row['built_sqm']} מ\"ר | **מגרש:** {row['plot_sqm']} מ\"ר")
                st.write(f"🛏️ **חדרים:** {row['bedrooms']} חדרים | 🛁 {row['bathrooms']} רחצה")
                st.write(f"🏊‍♂️ **בריכה:** {'כן' if row['has_pool'] else 'לא'} | 🌊 **נוף לים:** {'כן' if row['sea_view'] else 'לא'}")
                
            with col3:
                st.metric("🏆 ציון משוקלל סופי", f"{row['total_score']} / 10")
                st.caption(f"פיזי: {row['physical_score']} | מיקום: {row['location_score']} | Airbnb: {row['airbnb_score']}")
                if row['url'] != "N/A":
                    st.markdown(f"[🔗 קישור למודעה המקורית]({row['url']})")
                    
            with col4:
                st.write("")
                st.write("")
                # כפתור מחיקה
                if st.button("🗑️ מחק", key=f"del_{row['id']}"):
                    st.session_state.properties = [p for p in st.session_state.properties if p["id"] != row["id"]]
                    save_data(st.session_state.properties)
                    st.warning("הנכס נמחק מהרשימה.")
                    st.rerun()
