import streamlit as st
import json
import requests
from openai import OpenAI

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="AI Sales Agent", page_icon="🤖", layout="wide")

st.title("🤖 Otonom B2B Satış Ajanı")
st.markdown("Bu ajan, belirlediğiniz hedef kitleyi Google'da arar, analiz eder ve taslak mail yazar.")

# --- SIDEBAR: API ANAHTARLARI ---
with st.sidebar:
    st.header("🔑 API Ayarları")
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="GPT-4 için gerekli")
    serper_api_key = st.text_input("Serper.dev API Key", type="password", help="Google Araması için gerekli")
    
    st.divider()
    st.markdown("### 🎯 Hedef Kitle")
    target_position = st.text_input("Hedef Ünvan", "Logistics Manager")
    target_industry = st.text_input("Sektör", "Shipping")
    target_location = st.text_input("Lokasyon", "Dubai")
    
    st.divider()
    st.markdown("### 📦 Ürün Bilgisi")
    product_name = st.text_input("Ürün Adı", "RouteOpt")
    value_proposition = st.text_area("Değer Önerisi (Value Prop)", "Yapay zeka ile rota optimizasyonu yaparak yakıt maliyetlerini %20 düşürüyoruz.")

# --- TOOL FONKSİYONLARI ---

def google_search(position, industry, location, api_key):
    """Google Serper API ile arama yapar."""
    url = "https://google.serper.dev/search"
    query = f'site:linkedin.com/in/ "{position}" "{industry}" "{location}"'
    payload = json.dumps({"q": query, "num": 5})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def send_email_mock(to_name, content):
    """Mail gönderim simülasyonu."""
    return {"status": "success", "message": f"Email {to_name} kişisine iletildi."}

# --- AJAN MANTIĞI ---

def run_agent():
    if not openai_api_key or not serper_api_key:
        st.error("Lütfen önce sol menüden API anahtarlarını girin.")
        return

    client = OpenAI(api_key=openai_api_key)
    
    # UI'da Log Alanı Oluştur
    log_container = st.container()
    
    with log_container:
        st.info("🚀 Ajan başlatılıyor...")
        
        # 1. ADIM: ARAŞTIRMA
        st.write(f"🔎 **Araştırılıyor:** {target_position} in {target_location} ({target_industry})")
        search_results = google_search(target_position, target_industry, target_location, serper_api_key)
        
        leads = []
        if "organic" in search_results:
            for item in search_results["organic"]:
                leads.append({
                    "name": item.get("title", "").split("-")[0].strip(),
                    "link": item.get("link"),
                    "snippet": item.get("snippet")
                })
        else:
            st.error("Sonuç bulunamadı veya API hatası.")
            return

        st.success(f"✅ {len(leads)} adet potansiyel müşteri bulundu.")
        st.json(leads) # Ham veriyi göster

        # 2. ADIM: ANALİZ VE MAİL YAZIMI (GPT-4)
        st.write("✍️ **GPT-4 Müşterileri Analiz Ediyor ve Mail Yazıyor...**")
        
        for lead in leads:
            with st.expander(f"📧 Taslak: {lead['name']}"):
                prompt = f"""
                Sen bir B2B Satış Uzmanısın.
                
                MÜŞTERİ:
                İsim: {lead['name']}
                Bağlam: {lead['snippet']}
                
                BİZİM ÜRÜN:
                Ürün: {product_name}
                Değer: {value_proposition}
                
                GÖREV:
                Bu müşteriye özel, samimi ve kısa bir soğuk satış maili yaz. 
                Asla "Umarım bu mail sizi iyi bulur" gibi klişeler kullanma.
                Doğrudan konuya gir ve bağlamı kullanarak ilgisini çek.
                Sadece mail içeriğini döndür.
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}]
                )
                
                email_content = response.choices[0].message.content
                st.text_area("Mail İçeriği", email_content, height=200)
                
                if st.button(f"Gönder ({lead['name']})", key=lead['link']):
                    # Burada gerçek mail atma fonksiyonu çağrılır
                    res = send_email_mock(lead['name'], email_content)
                    st.toast(f"Mail gönderildi: {lead['name']}", icon="✅")

# --- UI TETİKLEYİCİSİ ---
if st.button("Ajanı Çalıştır", type="primary"):
    run_agent()
