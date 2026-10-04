import os
import json
import streamlit as st
import pandas as pd
from PIL import Image
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

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

# חיבור ל-Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        df = conn.read(ttl=0)
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception:
        return []

def save_data(data_list):
    df = pd.DataFrame(data_list)
    conn.update(data=df)

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
st.caption("הוסיפו צילומי מסך או טקסט של מודעה, וה-AI יחלץ את הנתונים וידרג אותה אוטומטית.")

with st.expander("➕ הוספת נכס חדש (לחץ להרחבה)", expanded=True):
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        added_by = st.selectbox("שם בן המשפחה המוסיף:", ["דודי", "גל", "מאיר/פזית", "אחר"])
        property_url = st.text_input("קישור למודעה / פוסט (אופציונלי):")
        property_text = st.text_area("טקסט המודעה / הערות נוספות:", placeholder="הדבק כאן טקסט במידת הצורך...")
        
    with col_input2:
        uploaded_image_1 = st.file_uploader("📷 צילום מסך 1 (חלק ראשי):", type=["jpg", "jpeg", "png"], key="img1")
        if uploaded_image_1 is not None:
            st.success(f"✔️ תמונה 1 נטענה: {uploaded_image_1.name}")
            st.image(uploaded_image_1, width=120)
            
        st.write("---")
        
        uploaded_image_2 = st.file_uploader("📷 צילום מסך 2 (המשך המודעה - אופציונלי):", type=["jpg", "jpeg", "png"], key="img2")
        if uploaded_image_2 is not None:
            st.success(f"✔️ תמונה 2 נטענה: {uploaded_image_2.name}")
            st.image(uploaded_image_2, width=120)
        
    images_to_process = [img for img in [uploaded_image_1, uploaded_image_2] if img is not None]

    if st.button("🚀 נתח והוסף נכס ללוח", use_container_width=True):
        if not property_text and not images_to_process and not property_url:
            st.error("יש לספק לפחות צילום מסך אחד, טקסט או קישור למודעה.")
        else:
            with st.spinner("מנוע ה-AI מנתח את הנתונים ושומר ב-Google Sheets..."):
                try:
                    combined_text = f"URL: {property_url}\n{property_text}" if property_url else property_text
                    parsed_data = analyze_with_gemini(user_text=combined_text, image_files=images_to_process)
                    
                    # רשימת הנתונים העדכנית
                    current_props = load_data()
                    parsed_data["id"] = len(current_props) + 1
                    parsed_data["added_by"] = added_by
                    parsed_data["url"] = property_url if property_url else "N/A"
                    
                    current_props.append(parsed_data)
                    save_data(current_props)
                    
                    st.session_state.properties = current_props
                    st.success(f"הנכס '{parsed_data['property_title']}' נשמר בהצלחה ב-Google Sheets!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בניתוח המודעה: {e}")

st.divider()

# ==========================================
# 4. הצגת טבלת ההשוואה והמחיקה
# ==========================================
st.subheader("📋 טבלת השוואת נכסים (ממוינת לפי ציון משוקלל)")

# טעינת נתונים עדכנית ישירות מ-Google Sheets
st.session_state.properties = load_data()

if not st.session_state.properties:
    st.info("עדיין לא הוספו נכסים. השתמשו בטופס למעלה כדי להוסיף את הנכס הראשון!")
else:
    df = pd.DataFrame(st.session_state.properties)
    df = df.sort_values(by="total_score", ascending=False)
    
    excel_file = "greece_properties_comparison.xlsx"
    df.to_excel(excel_file, index=False)
    with open(excel_file, "rb") as f:
        st.download_button(
            label="📥 הורד טבלה מעודכנת לקובץ Excel",
            data=f,
            file_name="Greece_Properties_Comparison.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
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
                if st.button("🗑️ מחק", key=f"del_{row['id']}"):
                    updated_props = [p for p in st.session_state.properties if p["id"] != row["id"]]
                    save_data(updated_props)
                    st.session_state.properties = updated_props
                    st.warning("הנכס נמחק.")
                    st.rerun()
