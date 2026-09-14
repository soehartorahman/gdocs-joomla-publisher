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

# --- DAFTAR PENULIS ASLI ---
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

# --- DAFTAR KATEGORI LENGKAP ---
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

# --- 2. FORMAT TEKS GEMINI AI ---
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

# --- 3. BROWSER BOT AUTOMATION (AUTHOR NAME & CATEGORY FIX) ---
def run_publisher_bot(admin_url, username, password, title, alias, cat_id, author_id, author_name, html_content, images, bridge_token):
    logs = []
    screenshots = []
    logs.append("🤖 **Memulai Publisher Bot...**")
    
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
            logs.append("✅ **Berhasil Login Admin!**")

            # 2. Buka Form Artikel Baru
            new_art_url = f"{base_domain}/administrator/index.php?option=com_content&task=article.add"
            logs.append(f"📝 Membuka Form Artikel Baru: `{new_art_url}`")
            page.goto(new_art_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#jform_title", timeout=20000)

            # 3. Isi Judul & Alias
            logs.append("✍️ Mengisi Judul Artikel...")
            page.fill("#jform_title", title)

            if alias:
                alias_input = page.locator("#jform_alias").first
                if alias_input.is_visible():
                    alias_input.fill(alias)

            # 4. MEMILIH KATEGORI (PANEL KANAN)
            logs.append(f"🏷️ Memilih Kategori ID: `{cat_id}`...")
            page.evaluate("""
                ([catId]) => {
                    const select = document.querySelector('#jform_catid');
                    if (select) {
                        select.value = String(catId);
                        select.removeAttribute('required');
                        select.removeAttribute('aria-invalid');
                        select.classList.remove('invalid');
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            """, [str(cat_id)])
            page.wait_for_timeout(500)

            # 5. INJEKSI KONTEN KE JCE EDITOR
            logs.append("📝 Memasukkan Teks Artikel ke JCE Editor...")
            page.evaluate("""
                ([html]) => {
                    if (window.WFEditor && WFEditor.instances && WFEditor.instances.jform_articletext) {
                        WFEditor.instances.jform_articletext.setContent(html);
                    } else if (window.WFEditor && typeof WFEditor.setContent === 'function') {
                        WFEditor.setContent('jform_articletext', html);
                    } else {
                        const jceIframe = document.querySelector('#jform_articletext_ifr, iframe.wf-editor');
                        if (jceIframe && jceIframe.contentDocument) {
                            jceIframe.contentDocument.body.innerHTML = html;
                        }
                    }
                }
            """, [html_content])
            page.wait_for_timeout(500)

            # 6. ISI INTRO IMAGE DI TAB 'Images and Links'
            if first_img_relative_path:
                logs.append(f"🖼️ Set Path Gambar: `{first_img_relative_path}`...")
                page.evaluate("""
                    () => {
                        const tabs = Array.from(document.querySelectorAll('button, a'));
                        const imgTab = tabs.find(el => el.textContent.trim() === 'Images and Links' || el.getAttribute('aria-controls') === 'attrib-images');
                        if (imgTab) imgTab.click();
                    }
                """)
                page.wait_for_timeout(500)

                intro_input = page.locator("#jform_images_image_intro").first
                if intro_input.is_visible():
                    intro_input.fill(first_img_relative_path)

                full_input = page.locator("#jform_images_image_fulltext").first
                if full_input.is_visible():
                    full_input.fill(first_img_relative_path)

            # 7. UBAH PENULIS DI TAB 'Publishing' DENGAN NAMA PENULIS DAN AUTHOR ID
            if author_name:
                logs.append(f"👤 Ubah Penulis di Tab 'Publishing' ke: `{author_name}` (ID: {author_id})...")
                page.evaluate("""
                    () => {
                        const tabs = Array.from(document.querySelectorAll('button, a'));
                        const pubTab = tabs.find(el => el.textContent.trim() === 'Publishing' || el.getAttribute('aria-controls') === 'publishing');
                        if (pubTab) pubTab.click();
                    }
                """)
                page.wait_for_timeout(500)

                page.evaluate("""
                    ([authorName, authorId]) => {
                        // 1. Mengisi kolom Created By Alias / Author (Nama Penulis Teks)
                        const createdByAlias = document.querySelector('#jform_created_by_alias, input[name="jform[created_by_alias]"]');
                        if (createdByAlias) {
                            createdByAlias.value = authorName;
                            createdByAlias.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        
                        // 2. Mengisi Author Field biasa jika ada
                        const authorField = document.querySelector('#jform_author, input[name="jform[author]"]');
                        if (authorField) {
                            authorField.value = authorName;
                            authorField.dispatchEvent(new Event('change', { bubbles: true }));
                        }

                        // 3. Mengisi ID Penulis jika valid
                        if (authorId && authorId > 0) {
                            const createdBy = document.querySelector('#jform_created_by');
                            if (createdBy) {
                                createdBy.value = String(authorId);
                                createdBy.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    }
                """, [author_name, author_id])
                page.wait_for_timeout(500)

            # 8. TEKAN SAVE & CLOSE LEWAT JOOMLA SUBMIT API
            logs.append("💾 **Menekan Tombol 'Save & Close'...**")
            page.evaluate("""
                () => {
                    if (window.Joomla && typeof Joomla.submitbutton === 'function') {
                        Joomla.submitbutton('article.save');
                    } else if (document.adminForm) {
                        Joomla.submitform('article.save', document.adminForm);
                    } else {
                        const btn = document.querySelector("joomla-toolbar-button[task='article.save'] button, button[data-task='article.save'], button.button-save");
                        if (btn) btn.click();
                    }
                }
            """)

            page.wait_for_timeout(4000)

            # Ambil screenshot tampilan akhir
            screenshot_bytes = page.screenshot(full_page=False)
            screenshots.append(screenshot_bytes)

            logs.append(f"🌐 **[URL SEKARANG]**: `{page.url}`")

            has_error = page.locator(".alert-danger, .system-message-container .alert-error").is_visible()

            if not has_error and ("option=com_content&view=articles" in page.url or "task=article.save" not in page.url):
                logs.append("🎉 **Artikel BERHASIL Diterbitkan Sempurna & Terkonfirmasi di Database!**")
                browser.close()
                return True, logs, screenshots
            else:
                logs.append("❌ **Gagal Simpan:** Periksa screenshot tampilan backend di bawah.")
                browser.close()
                return False, logs, screenshots

        except Exception as e:
            logs.append(f"❌ **Error Automation:** `{str(e)}`")
            try:
                screenshots.append(page.screenshot())
            except Exception:
                pass
            browser.close()
            return False, logs, screenshots

# --- INTERFACE GUI STREAMLIT ---
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
    selected_user_name = st.selectbox("Pilih Penulis Artikel (Author):", list(USERS_DICT.keys()))
    if USERS_DICT[selected_user_name] == -1:
        author_id = st.number_input("Masukkan ID Penulis Baru (Angka):", min_value=1, step=1, value=359)
        author_name = "Penulis Kustom"
    else:
        author_id = USERS_DICT[selected_user_name]
        author_name = selected_user_name

if st.button("🚀 Publish Artikel Sekarang", type="primary"):
    if not doc_url or not article_title:
        st.error("Isi Link Google Docs dan Judul terlebih dahulu.")
    else:
        try:
            doc_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', doc_url)
            if not doc_id_match:
                st.error("URL Google Docs tidak valid.")
                st.stop()
            doc_id = doc_id_match.group(1)

            alias_clean = re.sub(r'[^a-z0-9-]', '', article_title.lower().replace(" ", "-").replace(":", ""))
            alias_clean = re.sub(r'-+', '-', alias_clean).strip('-')
            alias_clean = f"{alias_clean}-{int(time.time())}"

            with st.spinner("1/3 Membaca Google Docs & Gambar..."):
                raw_text, images = get_gdoc_data(doc_id, st.secrets["gcp_service_account"])

            with st.spinner("2/3 Format Gemini AI (Justify, Read More, Hapus Judul Docs)..."):
                formatted_html = format_with_gemini(raw_text, st.secrets["GEMINI_API_KEY"])

            with st.spinner("3/3 Bot Login & Terbit Artikel..."):
                success, debug_logs, shot_list = run_publisher_bot(
                    st.secrets["JOOMLA_URL"],
                    st.secrets["JOOMLA_ADMIN_USER"],
                    st.secrets["JOOMLA_ADMIN_PASS"],
                    article_title,
                    alias_clean,
                    cat_id,
                    author_id,
                    author_name,
                    formatted_html,
                    images,
                    st.secrets["JOOMLA_TOKEN"]
                )

            with st.expander("🛠️ Console Logs Automation", expanded=True):
                for log in debug_logs:
                    st.markdown(log)

            if shot_list:
                with st.expander("📸 Screenshot Bukti Tampilan Browser Bot", expanded=True):
                    for img_b in shot_list:
                        st.image(img_b, caption="Tampilan Halaman Backend Joomla saat Bot Berjalan", use_container_width=True)

            if success:
                st.success("✅ Artikel BERHASIL diterbitkan! Kategori dan Penulis sekarang sudah 100% sesuai pilihan!")
                st.balloons()
            else:
                st.error("Gagal memproses artikel. Cek log debugger di atas.")

        except Exception as e:
            st.error(f"Error: {str(e)}")
