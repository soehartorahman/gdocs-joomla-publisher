import streamlit as st
import re
import requests
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="GDocs to Joomla Publisher", page_icon="🚀", layout="centered")

st.title("🚀 Auto-Publisher GDocs ke Joomla 5")
st.caption("Pilih Author & Kategori langsung dari Joomla")

# --- 1. FUNGSI FETCH DATA DARI JOOMLA API ---
@st.cache_data(ttl=300)  # Cache hasil selama 5 menit agar aplikasi tidak lambat
def get_joomla_users(joomla_url, joomla_token):
    headers = {"Authorization": f"Bearer {joomla_token}"}
    url = f"{joomla_url}/users"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json().get("data", [])
        # Kembalikan dict format { 'Nama (username)': id }
        return {f"{u['attributes']['name']} (@{u['attributes']['username']})": u['id'] for u in data}
    return {}

@st.cache_data(ttl=300)
def get_joomla_categories(joomla_url, joomla_token):
    headers = {"Authorization": f"Bearer {joomla_token}"}
    url = f"{joomla_url}/content/categories"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json().get("data", [])
        # Kembalikan dict format { 'Nama Kategori': id }
        return {c['attributes']['title']: c['id'] for c in data}
    return {}

# --- 2. FUNGSI EKSTRAK GOOGLE DOCS ---
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

# --- 3. FUNGSI GEMINI AI ---
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

# --- 4. FUNGSI PUBLISH JOOMLA ---
def publish_to_joomla(title, html_content, images, cat_id, author_id, joomla_url, joomla_token):
    headers = {"Authorization": f"Bearer {joomla_token}"}
    
    # Upload Gambar
    for idx, img_bytes in enumerate(images, start=1):
        filename = f"article_img_{idx}.jpg"
        files = {'file': (filename, img_bytes, 'image/jpeg')}
        media_url = f"{joomla_url}/media/files/images"
        
        res_media = requests.post(media_url, headers=headers, files=files)
        if res_media.status_code in [200, 201]:
            img_path = res_media.json()['data']['attributes']['path']
            img_tag = f'<p><img src="/{img_path}" alt="Gambar Artikel {idx}" /></p>'
            html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", img_tag)

    # Buat Artikel
    payload = {
        "title": title,
        "alias": re.sub(r'[^a-zA-Z0-9-]', '', title.lower().replace(" ", "-")),
        "articletext": html_content,
        "catid": int(cat_id),
        "state": 1,
        "created_by": int(author_id),
        "language": "*"
    }
    
    article_url = f"{joomla_url}/content/articles"
    res_article = requests.post(article_url, headers=headers, json=payload)
    return res_article.status_code in [200, 201], res_article.json()


# --- TAMPILAN UNTUK STREAMLIT ---

# Ambill data User & Category dari Joomla via API
try:
    joomla_url = st.secrets["JOOMLA_URL"]
    joomla_token = st.secrets["JOOMLA_TOKEN"]
    
    users_dict = get_joomla_users(joomla_url, joomla_token)
    categories_dict = get_joomla_categories(joomla_url, joomla_token)
except Exception as e:
    st.error("Gagal terhubung ke Joomla API. Periksa Secrets (JOOMLA_URL & JOOMLA_TOKEN).")
    st.stop()

# Form Input
doc_url = st.text_input("Link Google Docs:")
article_title = st.text_input("Judul Artikel:")

col1, col2 = st.columns(2)

with col1:
    if categories_dict:
        selected_cat_name = st.selectbox("Pilih Kategori Artikel:", list(categories_dict.keys()))
        cat_id = categories_dict[selected_cat_name]
    else:
        cat_id = st.number_input("ID Kategori Joomla (Manual)", value=2)

with col2:
    if users_dict:
        selected_user_name = st.selectbox("Pilih Author (User Administrator):", list(users_dict.keys()))
        author_id = users_dict[selected_user_name]
    else:
        author_id = st.number_input("ID User Author (Manual)", value=42)

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
                success, response = publish_to_joomla(
                    article_title, 
                    formatted_html, 
                    images, 
                    cat_id, 
                    author_id, 
                    joomla_url, 
                    joomla_token
                )

            if success:
                st.success(f"✅ Artikel berhasil terbit dengan Author ID: {author_id}!")
                st.balloons()
            else:
                st.error(f"Gagal publish: {response}")

        except Exception as e:
            st.error(f"Error: {str(e)}")
