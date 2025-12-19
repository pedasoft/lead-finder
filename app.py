import streamlit as st
import pandas as pd
import requests
import json
import io
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="AI Sales Hunter (Apollo Edition)", page_icon="🚀", layout="wide")

st.title("🚀 B2B Sales Agent: Google + Apollo Entegrasyonu")
st.markdown("Google ile adayları bulun, Apollo API ile verileri zenginleştirin ve Excel'e aktarın.")

# --- SIDEBAR: AYARLAR ---
with st.sidebar:
    st.header("⚙️ Konfigürasyon")
    
    st.subheader("1. API Anahtarları")
    openai_api_key = st.text_input("OpenAI API Key", type="password")
    serper_api_key = st.text_input("Serper (Google) API Key", type="password")
    apollo_api_key = st.text_input("Apollo.io API Key", type="password", help="Enrichment için gereklidir.")
    
    st.divider()
    
    st.subheader("2. Hedef Kitle")
    target_position = st.text_input("Ünvan", "Marketing Manager")
    target_industry = st.text_input("Sektör", "SaaS")
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

def parse_profile(item):
    """LinkedIn başlığından Ad, Ünvan ve Şirketi ayıklar."""
    title = item.get("title", "")
    parts = title.split("-")
    
    name = parts[0].strip() if len(parts) >= 1 else "Bilinmiyor"
    role = parts[1].strip() if len(parts) >= 2 else "Bilinmiyor"
    # Şirket ismindeki " | LinkedIn" vb. temizle
    company = parts[2].split("|")[0].strip() if len(parts) >= 3 else "Bilinmiyor"
        
    return name, role, company

def find_email_apollo(name, company, api_key):
    """
    Apollo.io /people/match endpointini kullanarak mail bulur.
    """
    if not api_key:
        return "API Yok", "Veri Çekilemedi"

    url = "https://api.apollo.io/v1/people/match"
    
    # İsim soyisim ayrıştırma (Apollo first/last name ister)
    name_parts = name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    payload = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": company
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache'
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        if "person" in data and data["person"]:
            email = data["person"].get("email", "Mail Gizli/Yok")
            return email, "✅ Apollo Match"
        else:
            return "Bulunamadı", "❌ Eşleşme Yok"
            
    except Exception as e:
        return "Hata", f"API Hatası: {str(e)}"

# --- ANA UYGULAMA ---

def run_app():
    if not serper_api_key or not apollo_api_key:
        st.warning("⚠️ Lütfen sol menüden Serper ve Apollo API anahtarlarını girin.")
        return

    if st.button("🚀 Taramayı Başlat", type="primary"):
        
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
        
        # 2. ADIM: APOLLO ENRICHMENT
        status_box.write(f"🧩 {len(items)} profil bulundu. Apollo ile zenginleştiriliyor...")
        
        progress_bar = status_box.progress(0)
        total_items = len(items)
        
        for i, item in enumerate(items):
            # Parsing
            name, role, company = parse_profile(item)
            linkedin_url = item.get("link")
            snippet = item.get("snippet")
            
            # Apollo API Çağrısı
            email, status = find_email_apollo(name, company, apollo_api_key)
            
            processed_data.append({
                "Ad Soyad": name,
                "Ünvan": role,
                "Şirket": company,
                "E-Posta": email,
                "Durum": status,
                "LinkedIn URL": linkedin_url,
                "Bağlam": snippet
            })
            
            progress_bar.progress((i + 1) / total_items)
            
        status_box.update(label="✅ Tarama ve Zenginleştirme Tamamlandı!", state="complete", expanded=False)
        
        # 3. ADIM: TABLO GÖSTERİMİ
        df = pd.DataFrame(processed_data)
        
        st.subheader(f"📋 Sonuçlar ({len(df)} Kayıt)")
        
        # Düzenlenebilir Grid
        edited_df = st.data_editor(
            df,
            column_config={
                "LinkedIn URL": st.column_config.LinkColumn("Profil"),
                "E-Posta": st.column_config.TextColumn("E-Posta", validate="^[\w\.-]+@[\w\.-]+\.\w+$"),
                "Durum": st.column_config.Column("Apollo Durumu", width="medium")
            },
            hide_index=True,
            use_container_width=True
        )
        
        # 4. ADIM: EXCEL İNDİRME
        col1, col2 = st.columns([1, 4])
        
        with col1:
            # Excel Buffer
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='Leads')
            
            st.download_button(
                label="📥 Excel İndir",
                data=output.getvalue(),
                file_name=f"Leads_{target_industry}_{target_location}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        # 5. ADIM: AI İLE MAİL OLUŞTURMA (Opsiyonel)
        if openai_api_key:
            st.divider()
            st.subheader("📧 Seçili Kişiye AI Mail Yaz")
            
            # Kullanıcı listeden birini seçsin
            selected_person = st.selectbox("Mail yazılacak kişiyi seçin:", df["Ad Soyad"] + " - " + df["Şirket"])
            
            if st.button("Mail Taslağı Oluştur"):
                # Seçilen kişinin tüm verisini bul
                person_data = df[df["Ad Soyad"] + " - " + df["Şirket"] == selected_person].iloc[0]
                
                prompt = f"""
                Sen üst düzey bir B2B Satış Temsilcisisin.
                ALICI: {person_data['Ad Soyad']}, {person_data['Ünvan']}, {person_data['Şirket']}
                BAĞLAM: {person_data['Bağlam']}
                
                Bu kişiye, onun şirketi ve pozisyonuyla ilgili, profesyonel ama samimi bir tanışma maili yaz.
                Apollo'dan gelen veriyi kullan. Asla "Umarım iyisinizdir" gibi klişelerle başlama.
                """
                
                client = OpenAI(api_key=openai_api_key)
                res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user", "content": prompt}])
                
                st.info(f"Kime: {person_data['E-Posta']}")
                st.text_area("Mail Taslağı", res.choices[0].message.content, height=250)

if __name__ == "__main__":
    run_app()
