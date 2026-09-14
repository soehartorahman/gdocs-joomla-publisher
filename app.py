import streamlit as st
import datetime
import time
import re
import os
import requests
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="GDocs to Joomla Publisher", page_icon="🚀", layout="centered")

st.title("🚀 Auto-Publisher GDocs ke Joomla 5")
st.caption("BMKG GAW Bariri - Powered by Gemini AI & Playwright Bot")

# --- DAFTAR PENULIS ASLI (AKUN BOT HIDDEN DARI GUI) ---
USERS_DICT = {
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
    "Administrator (admin)": 348,
    "➕ Input Manual ID Penulis Baru...": -1
}

# --- DAFTAR KATEGORI LENGKAP (A-Z) ---
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

# --- 2. FORMAT TEKS GEMINI AI (JUSTIFY, BUANG JUDUL DOCS, INSERT READ MORE) ---
def format_with_gemini(raw_text, gemini_key):
    client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
    Ubah teks draf artikel berikut menjadi format HTML artikel blog Joomla yang rapi.
    
    Aturan Penting:
    1. HAPUS/BUANG teks judul artikel yang ada di dalam draf (baik posisi di atas maupun di bawah gambar pertama).
    2. JANGAN sertakan tag <h1> untuk judul di dalam body HTML.
    3. Bungkus SELURUH konten artikel dalam kontainer <div style="text-align: justify;"> agar paragraf rata kiri-kanan.
    4. Masukkan tag pembatas Joomla `<hr id="system-readmore" />` persis setelah paragraf pertama (sebelum <h2> atau gambar kedua) untuk memicu fitur "Read More".
    5. Gunakan tag HTML standar seperti <h2>, <h3>, <p>, <ul>, <li>, <strong>.
    6. JANGAN HAPUS atau merusak tag placeholder gambar seperti [IMAGE_PLACEHOLDER_1], [IMAGE_PLACEHOLDER_2], dst.
    7. Kembalikan HANYA kode HTML tanpa format markdown (jangan gunakan ```html).

    Teks Asli:
    {raw_text}
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    return response.text

# --- 3. BROWSER BOT AUTOMATION (NAVIGASI MENU CONTENT) ---
def run_publisher_bot(admin_url, username, password, title, alias, cat_id, author_id, html_content, images, bridge_token):
    logs = []
    logs.append("🤖 **Memulai Browser Bot (Headless Mode)...**")
    
    base_domain = str(admin_url).replace('/administrator', '').replace('/index.php', '').strip().rstrip('/')
    if not base_domain.startswith("http"):
        base_domain = f"https://{base_domain}"
        
    admin_login_url = f"{base_domain}/administrator/index.php"
    endpoint_url = f"{base_domain}/api/push.php"

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    unique_timestamp = now_dt.strftime("%Y%m%d%H%M%S")
    first_img_relative_path = ""

    # A. UPLOAD GAMBAR VIA BRIDGE PUSH.PHP
    for idx, img_bytes in enumerate(images, start=1):
        filename = f"article_{unique_timestamp}_{cat_id}_{idx}.jpg"
        files = {'file': (filename, img_bytes, 'image/jpeg')}
        media_headers = {"X-Joomla-Token": bridge_token}
        
        try:
            res_media = requests.post(endpoint_url, headers=media_headers, files=files, timeout=15)
            logs.append(f"🖼️ Upload Gambar {idx} Status: `{res_media.status_code}`")
        except Exception as e:
            logs.append(f"⚠️ Upload Gambar {idx} Error: `{str(e)}`")

        if idx == 1:
            first_img_relative_path = f"images/Artikel/{filename}"

        img_src_url = f"{base_domain}/images/Artikel/{filename}?v={unique_timestamp}"
        img_tag = f'<p style="text-align: center;"><img src="{img_src_url}" alt="{title}" class="img-fluid rounded my-3" /></p>'
        html_content = html_content.replace(f"[IMAGE_PLACEHOLDER_{idx}]", img_tag)

    # B. PLAYWRIGHT AUTOMATION
    with sync_playwright() as p:
        # Fallback chromium Linux Streamlit Cloud
        executable_path = None
        if os.path.exists("/usr/bin/chromium"):
            executable_path = "/usr/bin/chromium"
        elif os.path.exists("/usr/bin/chromium-browser"):
            executable_path = "/usr/bin/chromium-browser"

        if executable_path:
            browser = p.chromium.launch(executable_path=executable_path, headless=True)
        else:
            browser = p.chromium.launch(headless=True)

        context = browser.new_context(viewport={'width': 1366, 'height': 768})
        page = context.new_page()

        try:
            # 1. Login Backend Administrator
            logs.append(f"🔑 Menuju halaman login admin: `{admin_login_url}`")
            page.goto(admin_login_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("input[name='username']", timeout=15000)

            page.fill("input[name='username']", username)
            page.fill("input[name='passwd']", password)
            page.click("button[type='submit']")
            page.wait_for_load_state("domcontentloaded")
            logs.append("✅ **Berhasil Login ke Dashboard Joomla!**")

            # 2. NAVIGASI MELALUI MENU CONTENT (SEPERTI MANUSIA)
            logs.append("📂 Membuka Sidebar Menu 'Content'...")
            
            # Coba klik menu Content pada sidebar kiri
            content_menu = page.locator("a:has-text('Content'), li#menu-content > a, nav#sidebar a[href*='com_content']")
            if content_menu.is_visible():
                content_menu.click()
                page.wait_for_timeout(500)

            # Klik ikon (+) pada Articles atau buka Articles
            logs.append("📝 Menuju halaman pembuatan Artikel Baru...")
            add_article_btn = page.locator("a[href*='task=article.add'], a:has-text('Articles') + a, button.button-new")
            
            if add_article_btn.is_visible():
                add_article_btn.click()
            else:
                # Direct fallback ke halaman pembuatan artikel
                page.goto(f"{base_domain}/administrator/index.php?option=com_content&task=article.add", wait_until="domcontentloaded")

            page.wait_for_load_state("domcontentloaded")

            # 3. Input Title & Alias
            title_input = page.locator("input[name='jform[title]'], #jform_title")
            title_input.wait_for(state="visible", timeout=20000)
            title_input.fill(title)

            if alias:
                alias_input = page.locator("input[name='jform[alias]'], #jform_alias")
                if alias_input.is_visible():
                    alias_input.fill(alias)

            # 4. Pilih Kategori
            cat_select = page.locator("select[name='jform[catid]'], #jform_catid")
            if cat_select.is_visible():
                cat_select.select_option(value=str(cat_id))

            # 5. Set Intro Image di Tab Images and Links
            if first_img_relative_path:
                logs.append("🖼️ Mengisi Intro Image & Full Text Image...")
                img_tab = page.locator("button[aria-controls='attrib-images'], a[href='#attrib-images']")
                if img_tab.is_visible():
                    img_tab.click()
                    page.wait_for_timeout(500)
                
                intro_input = page.locator("input[name='jform[images][image_intro]'], #jform_images_image_intro")
                if intro_input.is_visible():
                    intro_input.fill(first_img_relative_path)
                
                full_input = page.locator("input[name='jform[images][image_fulltext]'], #jform_images_image_fulltext")
                if full_input.is_visible():
                    full_input.fill(first_img_relative
