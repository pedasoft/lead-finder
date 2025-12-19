import streamlit as st
import pandas as pd
import requests
import io
from typing import Any, Dict, List, Tuple

# -----------------------------
# PAGE
# -----------------------------
st.set_page_config(
    page_title="Apollo Lead Finder (Search + Enrich)",
    page_icon="🛰️",
    layout="wide"
)

st.title("🛰️ Apollo Lead Finder (Tek Key)")
st.markdown("Apollo People Search → Bulk Enrich: Title + Location + Industry filtrele, isim/şirket/email getir.")

# -----------------------------
# SIDEBAR
# -----------------------------
with st.sidebar:
    st.header("⚙️ Ayarlar")

    apollo_api_key = st.text_input("Apollo API Key (Master önerilir)", type="password")

    st.divider()
    st.subheader("🎯 Filtreler")
    target_title = st.text_input("Title (job title)", "Quality Assurance Manager")
    target_location = st.text_input("Location (person location)", "Dubai")
    target_industry = st.text_input("Industry (organization industry)", "Pharma")

    per_page = st.slider("Sayfada kaç kişi (1-100)", 1, 100, 25)
    max_results = st.slider("Toplam sonuç limiti", 10, 300, 100, step=10)

    st.divider()
    st.subheader("🔎 Enrichment (email)")
    reveal_personal_emails = st.toggle("Kişisel emailleri reveal etmeyi dene", value=False)
    reveal_phone_number = st.toggle("Telefon reveal etmeyi dene", value=False)

# -----------------------------
# CONSTANTS
# -----------------------------
APOLLO_PEOPLE_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_BULK_MATCH_URL = "https://api.apollo.io/api/v1/people/bulk_match"

# -----------------------------
# HELPERS
# -----------------------------
def apollo_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "accept": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }

def safe_post(url: str, headers: Dict[str, str], params: Dict[str, Any] | None = None, payload: Dict[str, Any] | None = None, timeout: int = 30) -> Tuple[int, Dict[str, Any]]:
    r = requests.post(url, headers=headers, params=params, json=payload, timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return r.status_code, data

def chunked(lst: List[Any], n: int) -> List[List[Any]]:
    return [lst[i:i+n] for i in range(0, len(lst), n)]

def apollo_people_search(api_key: str, title: str, location: str, industry: str, per_page: int, page: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    People API Search email dönmez; sadece kişi listesi verir. :contentReference[oaicite:3]{index=3}
    """
    headers = apollo_headers(api_key)

    # Query params formatı: person_titles[]=..., person_locations[]=... :contentReference[oaicite:4]{index=4}
    params = {
        "per_page": per_page,
        "page": page,
        "person_titles[]": [title] if title else [],
        "person_locations[]": [location] if location else [],
    }

    # Industry filtresi Apollo’da query param olarak kullanılabiliyor (org industry). Bazı hesaplarda isim farklı olabilir;
    # çalışmazsa yine de search sonuç döner, sadece industry filtresi uygulanmayabilir.
    if industry:
        params["organization_industries[]"] = [industry]

    status, data = safe_post(APOLLO_PEOPLE_SEARCH_URL, headers=headers, params=params, payload=None, timeout=45)

    if status >= 400:
        msg = data.get("message") or data.get("error") or f"HTTP {status}"
        raise RuntimeError(f"Apollo People Search hata: {msg} | Detay: {data}")

    people = data.get("people", []) or []
    total_entries = int(data.get("total_entries", 0) or 0)
    return people, total_entries

def apollo_bulk_enrich(api_key: str, person_ids: List[str], reveal_personal: bool, reveal_phone: bool) -> List[Dict[str, Any]]:
    """
    Bulk People Enrichment: details[] içinde id ile enrich. :contentReference[oaicite:5]{index=5}
    """
    headers = apollo_headers(api_key)
    params = {
        "reveal_personal_emails": str(reveal_personal).lower(),
        "reveal_phone_number": str(reveal_phone).lower(),
    }
    payload = {"details": [{"id": pid} for pid in person_ids]}

    status, data = safe_post(APOLLO_BULK_MATCH_URL, headers=headers, params=params, payload=payload, timeout=45)

    if status >= 400:
        msg = data.get("message") or data.get("error") or f"HTTP {status}"
        raise RuntimeError(f"Apollo Bulk Enrich hata: {msg} | Detay: {data}")

    # Dönüş formatı hesaplara göre değişebiliyor; genelde "people" listesi veya "contacts"/"persons" benzeri gelir.
    # En güvenlisi: olası alanları dene.
    enriched = (
        data.get("people")
        or data.get("persons")
        or data.get("contacts")
        or data.get("matches")
        or []
    )

    # Bazı durumlarda wrapper olur:
    if isinstance(enriched, dict):
        enriched = enriched.get("people") or enriched.get("persons") or []

    return enriched if isinstance(enriched, list) else []

def pick_name_company_email(search_person: Dict[str, Any], enriched_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    pid = search_person.get("id", "")
    org = search_person.get("organization") or {}
    company = org.get("name", "") if isinstance(org, dict) else ""

    # Search response bazen last_name obfuscated döner. :contentReference[oaicite:6]{index=6}
    first = search_person.get("first_name", "") or ""
    last = search_person.get("last_name", "") or search_person.get("last_name_obfuscated", "") or ""

    email = ""
    status = "—"

    if pid and pid in enriched_map:
        ep = enriched_map[pid]
        # Enrichment genelde tam isim ve email içerir
        first = ep.get("first_name", first) or first
        last = ep.get("last_name", last) or last
        company = (ep.get("organization", {}) or {}).get("name", company) if isinstance(ep.get("organization"), dict) else company
        email = ep.get("email") or ""
        status = "✅ Enriched" if email else "⚠️ Enriched, email yok"

    full_name = (first + " " + last).strip()
    return {
        "Ad Soyad": full_name,
        "Şirket": company,
        "E-Posta": email if email else "Bulunamadı",
        "Apollo Person ID": pid,
        "Durum": status
    }

# -----------------------------
# APP
# -----------------------------
def run_app():
    if not apollo_api_key:
        st.warning("⚠️ Apollo API key gir.")
        return

    if st.button("🚀 Lead Bul (Apollo)", type="primary"):
        status_box = st.status("Başlıyor...", expanded=True)

        try:
            # 1) People Search (sayfalama)
            collected_people: List[Dict[str, Any]] = []
            page = 1
            total_entries = 0

            while len(collected_people) < max_results:
                status_box.write(f"🔎 People Search: page={page} ...")
                people, total_entries = apollo_people_search(
                    apollo_api_key,
                    target_title.strip(),
                    target_location.strip(),
                    target_industry.strip(),
                    per_page,
                    page
                )
                if not people:
                    break

                collected_people.extend(people)
                if len(people) < per_page:
                    break
                page += 1

            collected_people = collected_people[:max_results]
            if not collected_people:
                status_box.update(label="Sonuç yok", state="error")
                st.error("Filtrelerle kişi bulunamadı. Title/Location/Industry değiştir.")
                return

            status_box.write(f"✅ Bulunan kişi sayısı: {len(collected_people)} (toplam entries: {total_entries})")

            # 2) Bulk Enrich (10’lu batch)
            ids = [p.get("id") for p in collected_people if p.get("id")]
            ids = [x for x in ids if isinstance(x, str) and x.strip()]

            enriched_map: Dict[str, Dict[str, Any]] = {}
            batches = chunked(ids, 10)

            for i, batch in enumerate(batches, start=1):
                status_box.write(f"🧬 Bulk Enrich: {i}/{len(batches)} (batch size={len(batch)})")
                enriched_list = apollo_bulk_enrich(
                    apollo_api_key,
                    batch,
                    reveal_personal_emails,
                    reveal_phone_number
                )

                # Enriched kayıtları id ile map’le
                for ep in enriched_list:
                    if isinstance(ep, dict):
                        eid = ep.get("id") or ep.get("person_id")
                        if eid:
                            enriched_map[str(eid)] = ep

            # 3) Birleştir
            rows = [pick_name_company_email(p, enriched_map) for p in collected_people]
            df = pd.DataFrame(rows)

            status_box.update(label="✅ Tamamlandı!", state="complete", expanded=False)

            st.subheader(f"📋 Sonuçlar ({len(df)} kayıt)")
            edited_df = st.data_editor(df, hide_index=True, use_container_width=True)

            # Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                edited_df.to_excel(writer, index=False, sheet_name="Leads")

            st.download_button(
                label="📥 Excel İndir",
                data=output.getvalue(),
                file_name="apollo_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        except Exception as e:
            status_box.update(label="Hata!", state="error")
            st.error(str(e))
            st.info("Not: mixed_people/api_search endpoint'i master API key gerektirebilir. Key izinlerini kontrol et.")
            return

if __name__ == "__main__":
    run_app()
