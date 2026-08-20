import streamlit as st
import re
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

# --- DAFTAR KATEGORI LENGKAP (Nama: ID) ---
CATEGORIES_DICT = {
    "Iklim": 8,
    "Fakta Perubahan Iklim": 29,
    "Kimia Atmosfer": 9,
    "Profil": 10,
    "Berita": 11,
    "Karya Tulis": 12,
    "data iklim 2019": 13,
    "data iklim 2018": 14,
    "Musim": 15,
    "Buletin Bulanan": 16,
    "Cuaca": 17,
    "Gempabumi": 18,
    "Info Zona Integritas": 19,
    "Selengkapnya Tentang Zona Integritas": 21,
    "Dasboard": 23,
    "Artikel": 24,
    "Laporan Akuntabilitas Kinerja": 25,
    "Laporan Akuntansi Kinerja Instansi Pemerintah": 26,
    "GAW-sarium": 27,
    "Buletin Tahunan": 28,
    "Survei Kepuasan Masyarakat": 30,
    "Kimia Air Hujan": 31,
    "Analisis Hujan Bulanan": 32,
    "Info PM": 33,
    "FB Drag Helper": 34,
    "Pegawai": 35,
    "Peta Normal": 36,
    "Kaleidoskop": 37,
    "Zona Integritas": 38,
    "Dokumen ZI": 39,
    "➕ Input Manual ID Kategori Baru...": -1
}

# --- 1. FUNGSI EKSTRAK GOOGLE DOCS (TEXT & GAMBAR) ---
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

# --- 2. FUNGSI GEMINI AI (Gemini 3.6) ---
def format_with_gemini(raw_text, gemini_key):
    client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
    Ubah teks draf artikel berikut menjadi format HTML artikel blog yang rapi.
    
    Aturan:
    1. Gunakan tag HTML seperti <h2>, <h3>, <p>, <ul>, <li>, <strong>.
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

# --- 3. HELPER: BUAT FOLDER DENGAN LOG DEBUG ---
def ensure_joomla_folder(api_endpoint, folder_name, headers, logs):
    safe_folder = re.sub(r'[^a-zA-Z0-9_-]', '', folder_name.strip().replace(" ", "-"))
    if not safe_folder:
        safe_folder = "Artikel"

    # Fix Endpoint Media Folder Joomla 5 (Tanpa titik dua)
    create_folder_url = f"{api_endpoint}/media/folders/local/images"
    payload = {
        "name": safe_folder,
        "parent": "local/images"
    }

    try:
        res = requests.post(create_folder_url, headers=headers, json=payload, timeout=10)
        logs.append(f"📁 **Status Buat Folder (`images/{safe_folder}`):** `{res.status_code}`")
    except Exception as e:
        logs.append(f"⚠️ **Folder Warning/Exception:** `{str(e)}`")

    return safe_folder

# --- 4. FUNGSI PUBLISH UTAMA (FIXED PAYLOAD JOOMLA 5) ---
def publish_to_joomla(title, html_content, images, cat_id, author_id, joomla_url, joomla_token, selected_cat_name):
    base_clean = joomla_url.rstrip("/")
    if "index.php" not in base_clean:
        api_endpoint = f"{base_clean}/index.php/v1"
    elif not base_clean.endswith("/v1"):
        api_endpoint = f"{base_clean}/v1"
    else:
        api_endpoint = base_clean

    token_clean = joomla_token.strip()

    headers = {
        "X-Joomla-Token": token_clean,
        "Authorization": f"Bearer {token_clean}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.api+json"
    }

    logs = []
    logs.append(f"🔍 **BASE API ENDPOINT:** `{api_endpoint}`")

    # A. CEK / BUAT FOLDER OTOMATIS
    folder_target = ensure_joomla_folder(api_endpoint, selected_cat_name, headers, logs)

    # B. UPLOAD MEDIA (Fixed Path Endpoint)
    for idx, img_bytes in enumerate(images, start=1):
        filename = f"article_img_{idx}.jpg"
        media_url = f"{api_endpoint}/media/files/local/images/{folder_target}"
        files = {'file': (filename, img_bytes, 'image/jpeg')}
        media_headers = {
            "X-Joomla-Token": token_clean,
            "Authorization": f"Bearer {token_clean}",
            "Accept": "application/vnd.api+json"
        }
        
        try:
            res_media = requests.post(media_url, headers=media_headers, files=files, timeout=15)
            logs.append(f"🖼️ **Media {idx} Status:** `{res_media.status_code}` | **URL:** `{media_url}`")
            
            if res_media.status_code in [200, 201]:
                img_path = res_media.json()['data']['attributes']['path']
                img_tag = f'<p><img src="/{img_path}" alt="{title} - Gambar {idx}" /></p>'
                html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", img_tag)
            else:
                fallback_url = f"{api_endpoint}/media/files/local/images"
                res_fallback = requests.post(fallback_url, headers=media_headers, files=files, timeout=15)
                logs.append(f"🔄 **Media {idx} Fallback Root Status:** `{res_fallback.status_code}`")
                
                if res_fallback.status_code in [200, 201]:
                    img_path = res_fallback.json()['data']['attributes']['path']
                    img_tag = f'<p><img src="/{img_path}" alt="{title} - Gambar {idx}" /></p>'
                    html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", img_tag)
                else:
                    html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", "")
                    
        except Exception as e:
            html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", "")
            logs.append(f"❌ **Media Exception:** `{str(e)}`")

    # C. SANITASI ALIAS
    alias_clean = re.sub(r'[^a-z0-9-]', '', title.lower().replace(" ", "-").replace(":", "").replace("–", ""))
    alias_clean = re.sub(r'-+', '-', alias_clean).strip('-')

    # D. PAYLOAD DENGAN TIPE DATA RIGID (Sesuai Skema REST API Joomla 5)
    payload = {
        "data": {
            "type": "articles",
            "attributes": {
                "title": str(title).strip(),
                "alias": str(alias_clean),
                "articletext": str(html_content),
                "catid": int(cat_id),
                "state": 1,
                "created_by": int(author_id),
                "language": "*"
            }
        }
    }

    logs.append(f"📦 **Payload JSON Sent:**\n```json\n{payload}\n```")

    # E. POST ARTIKEL
    article_url = f"{api_endpoint}/content/articles"
    logs.append(f"🚀 **Target Post URL:** `{article_url}`")

    res_article = requests.post(article_url, headers=headers, json=payload, timeout=30)
    logs.append(f"📡 **Article Post Response Status:** `{res_article.status_code}`")

    try:
        response_data = res_article.json()
    except Exception:
        response_data = {"status_code": res_article.status_code, "text": res_article.text[:500]}

    return res_article.status_code in [200, 201], response_data, logs

# --- TAMPILAN APLIKASI STREAMLIT ---
doc_url = st.text_input("Link Google Docs:")
article_title = st.text_input("Judul Artikel:")

col1, col2 = st.columns(2)

with col1:
    selected_cat_name = st.selectbox("Pilih Kategori Artikel:", list(CATEGORIES_DICT.keys()))
    if CATEGORIES_DICT[selected_cat_name] == -1:
        cat_id = st.number_input("Masukkan ID Kategori Baru (Angka):", min_value=1, step=1, value=40)
    else:
        cat_id = CATEGORIES_DICT[selected_cat_name]

with col2:
    selected_user_name = st.selectbox("Pilih Author (User Administrator):", list(USERS_DICT.keys()))
    if USERS_DICT[selected_user_name] == -1:
        author_id = st.number_input("Masukkan ID User Baru (Angka):", min_value=1, step=1, value=364)
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

            with st.spinner("3/3 Upload ke Joomla 5..."):
                success, response, debug_logs = publish_to_joomla(
                    article_title, 
                    formatted_html, 
                    images, 
                    cat_id, 
                    author_id, 
                    st.secrets["JOOMLA_URL"], 
                    st.secrets["JOOMLA_TOKEN"],
                    selected_cat_name
                )

            # RENDER KOTAK DEBUGGER CONSOLE
            with st.expander("🛠️ Klik di sini untuk melihat Console Logs (Detail Titik Error)", expanded=True):
                for log in debug_logs:
                    st.markdown(log)

            if success:
                st.success("✅ Artikel berhasil terbit!")
                st.balloons()
            else:
                st.error(f"Gagal publish: {response}")

        except Exception as e:
            st.error(f"Error: {str(e)}")
