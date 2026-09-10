import streamlit as st
import datetime
import uuid
import threading
import time
import re
import json
import requests
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="GDocs to Joomla Publisher", page_icon="🚀", layout="centered")

st.title("🚀 Auto-Publisher GDocs ke Joomla 5")
st.caption("BMKG GAW Bariri - Powered by Gemini AI & Streamlit")

# --- DAFTAR USER LENGKAP (Nama: ID) ---
USERS_DICT = {
    "Administrator (admin)": 348,
    "Dian Paolo, S.Tr.Klim.": 359,
    "Galih Langit Pamungkas, S.Tr.Klim.": 362,
    "Henri Panggabean, S.Si": 357,
    "Hermanto Asima Nainggolan, S.Tr.": 363,
    "Laura Prastika,S.Tr": 351,
    "Mudayu Ekaning Prastiwi, S.Tr.Klim.": 355,
    "Muh.Soeharto Dwi Putra Rahman, S.Tr": 358,
    "Muhammad Hafizh Suwandi, S.Tr.Klim.": 349,
    "Santy Wulandari S.Tr": 360,
    "Solih Alfiandy,S.Tr": 353,
    "➕ Input Manual ID User Baru...": -1
}

# --- DAFTAR KATEGORI LENGKAP (DIURUTKAN SESUAI ABJAD A-Z) ---
CATEGORIES_DICT = {
    "Analisis Hujan Bulanan": 32,
    "Artikel": 24,
    "Berita": 11,
    "Buletin Bulanan": 16,
    "Buletin Tahunan": 28,
    "Cuaca": 17,
    "Dasboard": 23,
    "data iklim 2018": 14,
    "data iklim 2019": 13,
    "Dokumen ZI": 39,
    "FB Drag Helper": 34,
    "Fakta Perubahan Iklim": 29,
    "GAW-sarium": 27,
    "Gempabumi": 18,
    "Iklim": 8,
    "Info PM": 33,
    "Info Zona Integritas": 19,
    "Kaleidoskop": 37,
    "Karya Tulis": 12,
    "Kimia Air Hujan": 31,
    "Kimia Atmosfer": 9,
    "Laporan Akuntabilitas Kinerja": 25,
    "Laporan Akuntansi Kinerja Instansi Pemerintah": 26,
    "Musim": 15,
    "Pegawai": 35,
    "Peta Normal": 36,
    "Profil": 10,
    "Selengkapnya Tentang Zona Integritas": 21,
    "Survei Kepuasan Masyarakat": 30,
    "Zona Integritas": 38,
    "➕ Input Manual ID Kategori Baru...": -1
}

# --- BACKGROUND TRIGGER PEMBERSIS CACHE/REBUILD ASSET ---
def auto_trigger_joomla_cache(delay_seconds, bridge_url, token):
    """Menunggu durasi delay, lalu menembak push.php untuk memicu pembersihan cache."""
    time.sleep(delay_seconds)
    headers = {"X-Joomla-Token": token}
    try:
        requests.get(f"{bridge_url}?action=clear_cache", headers=headers, timeout=15)
    except Exception:
        pass

# --- 1. EKSTRAK TEKS & GAMBAR DARI GOOGLE DOCS ---
def get_gdoc_data(doc_id, service_account_info):
    creds = service_account.Credentials.from_service_account_info(
        service_account_info, 
        scopes=['https://www.googleapis.com/auth/documents.readonly']
    )
    service = build('docs', 'v1', credentials=creds)
    doc = service.documents().get(documentId=doc_id).execute()
    
    text_content = ""
    images = []
    
    for content in doc.get('body', {}).get('content', []):
        if 'paragraph' in content:
            for element in content['paragraph']['elements']:
                if 'textRun' in element:
                    text_content += element['textRun']['content']
                elif 'inlineObjectElement' in element:
                    obj_id = element['inlineObjectElement']['inlineObjectId']
                    img_obj = doc['inlineObjects'][obj_id]['inlineObjectProperties']['embeddedObject']
                    img_url = img_obj['imageProperties']['contentUri']
                    
                    img_bytes = requests.get(img_url).content
                    images.append(img_bytes)
                    text_content += f"\n[IMAGE_PLACEHOLDER_{len(images)}]\n"
                    
    return text_content, images

# --- 2. FORMAT TEKS DENGAN GEMINI AI ---
def format_with_gemini(raw_text, gemini_key):
    client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
    Ubah teks draf artikel berikut menjadi format HTML artikel blog yang rapi.
    
    Aturan:
    1. Gunakan tag HTML standar seperti <h2>, <h3>, <p>, <ul>, <li>, <strong>.
    2. JANGAN hapus atau ubah tag placeholder gambar seperti [IMAGE_PLACEHOLDER_1], [IMAGE_PLACEHOLDER_2], dst.
    3. Kembalikan HANYA kode HTML tanpa format markdown (jangan gunakan ```html).

    Teks Asli:
    {raw_text}
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    return response.text

# --- 3. PUBLISH KE JOOMLA VIA PUSH.PHP ---
def publish_to_joomla(title, html_content, images, cat_id, author_id, joomla_url, joomla_token):
    base_domain = "[https://gaw-bariri.bmkg.go.id](https://gaw-bariri.bmkg.go.id)".strip()
    endpoint_url = f"{base_domain}/api/push.php".strip()
    token_clean = str(joomla_token).strip()

    logs = []
    logs.append(f"🔍 **DIRECT BRIDGE ENDPOINT:** `{endpoint_url}`")

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    unique_timestamp = now_dt.strftime("%Y%m%d%H%M%S")

    first_image_relative_path = ""

    # A. UPLOAD GAMBAR DENGAN FILENAME UNIK & CACHE BUSTING
    for idx, img_bytes in enumerate(images, start=1):
        filename = f"article_{unique_timestamp}_{cat_id}_{idx}.jpg"
        
        upload_media_url = f"{base_domain}/api/push.php".strip()
        files = {'file': (filename, img_bytes, 'image/jpeg')}
        media_headers = {"X-Joomla-Token": token_clean}
        
        try:
            res_media = requests.post(upload_media_url, headers=media_headers, files=files, timeout=15)
            logs.append(f"🖼️ **Upload Gambar {idx} Status:** `{res_media.status_code}`")
        except Exception as e:
            logs.append(f"⚠️ **Upload Gambar {idx} Exception:** `{str(e)}`")

        if idx == 1:
            first_image_relative_path = f"images/Artikel/{filename}"

        img_src_url = f"{base_domain}/images/Artikel/{filename}?v={unique_timestamp}"
        img_tag = f'<p style="text-align: center;"><img src="{img_src_url}" alt="{title}" class="img-fluid rounded my-3" /></p>'
        
        html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", img_tag)

    # B. SANITASI TITLE & ALIAS UNIK
    clean_title = re.sub(r'[\xa0\t\n\r]', ' ', str(title)).strip()
    clean_title = clean_title.replace("–", "-").replace("—", "-")
    
    alias_clean = re.sub(r'[^a-z0-9-]', '', clean_title.lower().replace(" ", "-").replace(":", ""))
    alias_clean = re.sub(r'-+', '-', alias_clean).strip('-')
    alias_clean = f"{alias_clean}-{int(now_dt.timestamp())}"

    # C. FORMULA WAKTU (PUBLISH DATE DIBERI JEDA 3 MENIT/PENDING)
    created_time = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    publish_up_time = (now_dt + datetime.timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")

    # D. PAYLOAD IMAGES LENGKAP UNTUK SLIDER DEPAN
    images_payload = {}
    if first_image_relative_path:
        images_payload = {
            "image_intro": first_image_relative_path,
            "image_intro_alt": clean_title,
            "image_fulltext": first_image_relative_path,
            "image_fulltext_alt": clean_title
        }

    payload = {
        "title": clean_title,
        "alias": alias_clean,
        "articletext": html_content,
        "catid": int(cat_id),
        "created_by": int(author_id),
        "created": created_time,
        "publish_up": publish_up_time,
        "images": json.dumps(images_payload)
    }

    logs.append(f"📦 **Payload Sent to Bridge:**\n```json\n{payload}\n```")

    headers = {
        "X-Joomla-Token": token_clean,
        "Content-Type": "application/json"
    }

    res = requests.post(str(endpoint_url).strip(), headers=headers, json=payload, timeout=30)
    logs.append(f"📡 **Bridge Response Status:** `{res.status_code}`")

    try:
        response_data = res.json()
    except Exception:
        response_data = {"status_code": res.status_code, "text": res.text[:500]}

    if res.status_code in [200, 201]:
        threading.Thread(
            target=auto_trigger_joomla_cache, 
            args=(190, str(endpoint_url).strip(), token_clean)
        ).start()

    return res.status_code in [200, 201], response_data, logs

# --- INTERFACE STREAMLIT ---
doc_url = st.text_input("Link Google Docs:")
article_title = st.text_input("Judul Artikel:")

col1, col2 = st.columns(2)

with col1:
    selected_cat_name = st.selectbox("Pilih Kategori Artikel:", list(CATEGORIES_DICT.keys()))
    if CATEGORIES_DICT[selected_cat_name] == -1:
        cat_id = st.number_input("Masukkan ID Kategori Baru (Angka):", min_value=1, step=1, value=24)
    else:
        cat_id = CATEGORIES_DICT[selected_cat_name]

with col2:
    selected_user_name = st.selectbox("Pilih Author (User Administrator):", list(USERS_DICT.keys()))
    if USERS_DICT[selected_user_name] == -1:
        author_id = st.number_input("Masukkan ID User Baru (Angka):", min_value=1, step=1, value=348)
    else:
        author_id = USERS_DICT[selected_user_name]

if st.button("Publish Artikel", type="primary"):
    if not doc_url or not article_title:
        st.error("Isi Link Google Docs dan Judul terlebih dahulu.")
    else:
        try:
            doc_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', doc_url)
            if not doc_id_match:
                st.error("URL Google Docs tidak valid.")
                st.stop()
            doc_id = doc_id_match.group(1)

            with st.spinner("1/3 Membaca Google Docs & Gambar..."):
                raw_text, images = get_gdoc_data(doc_id, st.secrets["gcp_service_account"])

            with st.spinner("2/3 Formatting dengan Gemini AI..."):
                formatted_html = format_with_gemini(raw_text, st.secrets["GEMINI_API_KEY"])

            with st.spinner("3/3 Upload & Publish ke Joomla 5..."):
                success, response, debug_logs = publish_to_joomla(
                    article_title, 
                    formatted_html, 
                    images, 
                    cat_id, 
                    author_id, 
                    st.secrets["JOOMLA_URL"], 
                    st.secrets["JOOMLA_TOKEN"]
                )

            with st.expander("🛠️ Klik di sini untuk melihat Console Logs (Detail Titik Error)", expanded=True):
                for log in debug_logs:
                    st.markdown(log)
                
                if response:
                    st.write("📊 **Detail Diagnostik Response JSON:**")
                    st.json(response)

            if success:
                st.success("✅ Artikel berhasil dikirim dengan status Pending (akan terbit otomatis dalam 3 menit)!")
                st.balloons()
            else:
                st.error(f"Gagal publish: {response}")

        except Exception as e:
            st.error(f"Error: {str(e)}")
