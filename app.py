import streamlit as st
import pandas as pd
import requests
import json
import io
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="AI Sales Hunter (Smart Edition)", page_icon="🧠", layout="wide")

st.title("🧠 B2B Sales Agent: AI Destekli Ayrıştırma")
st.markdown("Google sonuçlarını AI ile analiz eder, şirketi doğru tespit eder ve Apollo ile zenginleştirir.")

# --- SIDEBAR: AYARLAR ---
with st.sidebar:
    st.header("⚙️ Konfigürasyon")
    
    st.subheader("1. API Anahtarları")
    openai_api_key = st.text_input("OpenAI API Key", type="password")
    serper_api_key = st.text_input("Serper (Google) API Key", type="password")
    apollo_api_key = st.text_input("Apollo.io API Key", type="password")
    
    st.divider()
    
    st.subheader("2. Hedef Kitle")
    target_position = st.text_input("Ünvan", "Quality Assurance Manager")
    target_industry = st.text_input("Sektör", "Pharma")
    target_location = st.text_input("Lokasyon", "Dubai")
    
    search_limit = st.slider("Sonuç Sayısı", 5, 20, 10)

# --- YARDIMCI FONKSİYONLAR ---

def google_search(position, industry, location, api_key, num_results):
    """Google Serper API ile arama yapar."""
    url = "https://google.serper.dev/search"
    query = f'site:linkedin.com/in/ "{position}" "{industry}" "{location}"'
    
    payload = json.dumps({"q": query, "num": num_results})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def extract_info_with_gpt(raw_title, snippet, client):
    """
    Basit string parçalama yerine GPT-4 kullanarak Ad, Ünvan ve Şirketi 'Zekice' ayıklar.
    """
    prompt = f"""
    Aşağıdaki LinkedIn arama sonucundan Kişi Adı, Ünvanı ve Şirket İsmini JSON formatında çıkar.
    
    GİRDİ:
    Title: {raw_title}
    Snippet: {snippet}
    
    KURALLAR:
    1. Eğer şirket ismi 'at' veya '@' kelimesinden sonraysa onu al. (Örn: Manager at Apple -> Şirket: Apple)
    2. Şirket ismi yoksa snippet kısmına bak.
    3. Hiçbir yerde yoksa "Bilinmiyor" yaz.
    4. Sadece saf JSON döndür.
    
    JSON FORMATI:
    {{
        "name": "Ad Soyad",
        "role": "Ünvan",
        "company": "Şirket Adı"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Hızlı ve ucuz model
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        return {"name": "Hata", "role": "Hata", "company": "Hata"}

def find_email_apollo(name, company, api_key):
    """Apollo.io ile mail bulur."""
    if not api_key or company == "Bilinmiyor":
        return "Veri Yok", "❌ Eksik Bilgi"

    url = "https://api.apollo.io/v1/people/match"
    
    name_parts = name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    payload = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": company
    }
    
    headers = {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        if "person" in data and data["person"]:
            email = data["person"].get("email")
            if email:
                return email, "✅ Eşleşti"
            else:
                return "Mail Gizli", "⚠️ Profil Var, Mail Yok"
        else:
            return "Bulunamadı", "❌ Eşleşme Yok"
            
    except Exception as e:
        return "Hata", f"API Hatası"

# --- ANA UYGULAMA ---

def run_app():
    if not serper_api_key or not apollo_api_key or not openai_api_key:
        st.warning("⚠️ Lütfen sol menüden TÜM API anahtarlarını girin (OpenAI dahil).")
        return

    if st.button("🚀 Akıllı Taramayı Başlat", type="primary"):
        
        client = OpenAI(api_key=openai_api_key)
        status_box = st.status("İşlem Başlatılıyor...", expanded=True)
        
        # 1. ADIM: GOOGLE ARAMASI
        status_box.write("🔍 Google taranıyor...")
        results = google_search(target_position, target_industry, target_location, serper_api_key, search_limit)
        
        if "organic" not in results:
            status_box.update(label="Hata oluştu!", state="error")
            st.error("Google'dan sonuç dönmedi.")
            return

        items = results["organic"]
        processed_data = []
        
        # 2. ADIM: AI PARSING ve APOLLO
        status_box.write(f"🧠 {len(items)} profil GPT-4 ile analiz ediliyor...")
        progress_bar = status_box.progress(0)
        total_items = len(items)
        
        for i, item in enumerate(items):
            raw_title = item.get("title", "")
            snippet = item.get("snippet", "")
            linkedin_url = item.get("link")
            
            # --- YENİLİK: AI İLE AYRIŞTIRMA ---
            parsed_info = extract_info_with_gpt(raw_title, snippet, client)
            
            name = parsed_info.get("name", "Bilinmiyor")
            role = parsed_info.get("role", "Bilinmiyor")
            company = parsed_info.get("company", "Bilinmiyor")
            
            # Apollo API Çağrısı
            email, status = find_email_apollo(name, company, apollo_api_key)
            
            processed_data.append({
                "Ad Soyad": name,
                "Ünvan": role,
                "Şirket": company,
                "E-Posta": email,
                "Durum": status,
                "LinkedIn URL": linkedin_url
            })
            
            progress_bar.progress((i + 1) / total_items)
            
        status_box.update(label="✅ İşlem Tamamlandı!", state="complete", expanded=False)
        
        # 3. ADIM: TABLO
        df = pd.DataFrame(processed_data)
        
        st.subheader(f"📋 Sonuçlar ({len(df)} Kayıt)")
        edited_df = st.data_editor(
            df,
            column_config={
                "LinkedIn URL": st.column_config.LinkColumn("Profil"),
                "E-Posta": st.column_config.TextColumn("E-Posta", validate="^[\w\.-]+@[\w\.-]+\.\w+$"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        # 4. ADIM: EXCEL
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='Leads')
        
        st.download_button(
            label="📥 Excel İndir",
            data=output.getvalue(),
            file_name=f"SmartLeads_{target_industry}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

if __name__ == "__main__":
    run_app()
