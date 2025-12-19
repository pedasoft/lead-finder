import streamlit as st
import pandas as pd
import requests
import json
import io
import re
from urllib.parse import urlparse
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="AI Sales Hunter (Domain Edition)", page_icon="🌐", layout="wide")

st.title("🌐 B2B Sales Agent: Domain Discovery Modu")
st.markdown("1. Google'dan Kişiyi Bul -> 2. GPT ile Şirketi Ayıkla -> 3. Domaini Bul -> 4. Apollo ile Nokta Atışı Yap")

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

def google_search_linkedin(position, industry, location, api_key, num_results):
    """Kişileri bulmak için LinkedIn araması."""
    url = "https://google.serper.dev/search"
    query = f'site:linkedin.com/in/ "{position}" "{industry}" "{location}"'
    
    payload = json.dumps({"q": query, "num": num_results})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def find_company_domain(company_name, api_key):
    """
    Şirket isminden Web Sitesini (Domain) bulur.
    Örnek: "Nestle" -> "nestle.com"
    """
    if company_name == "Bilinmiyor":
        return None

    url = "https://google.serper.dev/search"
    # Google'a "Nestle official website" diye soruyoruz
    query = f'{company_name} official website'
    
    payload = json.dumps({"q": query, "num": 1})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload)
        results = response.json()
        
        if "organic" in results and len(results["organic"]) > 0:
            link = results["organic"][0]["link"]
            # Linkten domaini temizle (https://www.nestle.com/jobs -> nestle.com)
            parsed_uri = urlparse(link)
            domain = parsed_uri.netloc.replace("www.", "")
            return domain
        return None
    except:
        return None

def extract_info_with_gpt(raw_title, snippet, client):
    """GPT-4 ile metin analizi."""
    prompt = f"""
    Aşağıdaki veriden Kişi, Ünvan ve Şirket bilgisini çıkar.
    
    GİRDİ:
    Title: {raw_title}
    Snippet: {snippet}
    
    KURALLAR:
    1. Şirket ismini 'at' veya '@' sonrasından almaya çalış.
    2. JSON formatında döndür.
    
    JSON:
    {{
        "name": "Ad Soyad",
        "role": "Ünvan",
        "company": "Şirket Adı"
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"name": "Hata", "role": "Hata", "company": "Bilinmiyor"}

def find_email_apollo_with_domain(name, domain, api_key):
    """
    Apollo'da Domain + İsim ile arama yapar. EN GÜÇLÜ YÖNTEMDİR.
    """
    if not api_key or not domain:
        return "Domain Yok", "❌ Domain Bulunamadı"

    url = "https://api.apollo.io/v1/people/match"
    
    name_parts = name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    payload = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "organization_domain": domain # <-- ARTIK İSİM DEĞİL DOMAIN ATIYORUZ
    }
    
    headers = {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        if "person" in data and data["person"]:
            email = data["person"].get("email")
            if email:
                return email, "✅ Eşleşti (Domain)"
            else:
                return "Mail Gizli", "⚠️ Profil Var, Mail Yok"
        else:
            # Domain eşleşmediyse son çare şirket adıyla dene (Opsiyonel)
            return "Bulunamadı", "❌ Apollo'da Yok"
            
    except Exception as e:
        return "Hata", "API Hatası"

# --- ANA UYGULAMA ---

def run_app():
    if not serper_api_key or not apollo_api_key or not openai_api_key:
        st.warning("⚠️ Lütfen tüm API anahtarlarını girin.")
        return

    if st.button("🚀 Domain Destekli Taramayı Başlat", type="primary"):
        
        client = OpenAI(api_key=openai_api_key)
        status_box = st.status("İşlem Başlatılıyor...", expanded=True)
        
        # 1. ADIM: GOOGLE ARAMASI
        status_box.write("🔍 Google'da kişiler aranıyor...")
        results = google_search_linkedin(target_position, target_industry, target_location, serper_api_key, search_limit)
        
        if "organic" not in results:
            status_box.update(label="Hata!", state="error")
            st.error("Sonuç yok.")
            return

        items = results["organic"]
        processed_data = []
        
        total_items = len(items)
        progress_bar = status_box.progress(0)
        
        for i, item in enumerate(items):
            # A. Parsing
            status_box.write(f"🧠 Analiz ediliyor: {i+1}/{total_items}")
            parsed_info = extract_info_with_gpt(item.get("title", ""), item.get("snippet", ""), client)
            
            name = parsed_info.get("name", "Bilinmiyor")
            role = parsed_info.get("role", "Bilinmiyor")
            company = parsed_info.get("company", "Bilinmiyor")
            
            # B. Domain Bulma (YENİ ADIM)
            domain = None
            if company != "Bilinmiyor":
                domain = find_company_domain(company, serper_api_key)
            
            # C. Apollo Arama (Domain ile)
            email, status = find_email_apollo_with_domain(name, domain, apollo_api_key)
            
            processed_data.append({
                "Ad Soyad": name,
                "Ünvan": role,
                "Şirket": company,
                "Website (Domain)": domain, # Yeni Sütun
                "E-Posta": email,
                "Durum": status,
                "LinkedIn URL": item.get("link")
            })
            
            progress_bar.progress((i + 1) / total_items)
            
        status_box.update(label="✅ Tamamlandı!", state="complete", expanded=False)
        
        # TABLO
        df = pd.DataFrame(processed_data)
        st.subheader(f"📋 Sonuçlar ({len(df)})")
        
        edited_df = st.data_editor(
            df,
            column_config={
                "LinkedIn URL": st.column_config.LinkColumn("Profil"),
                "Website (Domain)": st.column_config.LinkColumn("Web Sitesi"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        # EXCEL
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            edited_df.to_excel(writer, index=False, sheet_name='Leads')
        
        st.download_button(
            label="📥 Excel İndir",
            data=output.getvalue(),
            file_name="Leads_with_Domains.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

if __name__ == "__main__":
    run_app()
