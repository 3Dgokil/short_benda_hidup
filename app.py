import base64
import io
import json
import re
import time
import requests
import streamlit as st
from PIL import Image

st.set_page_config(
    page_title="ClarioHub 4-Phase Viral Shorts Studio",
    page_icon="🎬",
    layout="centered",
)

# --- Custom Styling for Mobile-Friendly Dark UI ---
st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 780px; }
      .phase-card {
        background: #111827;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 14px;
        white-space: pre-wrap;
        line-height: 1.55;
        font-size: 0.94rem;
      }
      .stButton > button { width: 100%; border-radius: 8px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session State Init ---
if "variation_count" not in st.session_state:
    st.session_state.variation_count = 0
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "previous_ideas" not in st.session_state:
    st.session_state.previous_ideas = []

STYLE_GUIDES = {
    "Otomatis (Paling Lucu Sesuai Bentuk & Fungsi Objek)": (
        "Pick the funniest, freshest comedic angle tailored strictly to the exact object's "
        "real shape, scale, or everyday function."
    ),
    "Sok Serius -> Gagal Konyol (Deadpan Contrast)": (
        "Deadpan Contrast: The object acts dead-serious, heroic, or overly dramatic like an "
        "action movie, then suffers an instant hilarious failure from something tiny and mundane."
    ),
    "Benda Memberontak dari Fungsinya (Object Logic)": (
        "Object Logic Rebellion: The everyday object develops a stubborn ego and hilariously "
        "refuses or sabotages its own real-world job."
    ),
    "Adu Gengsi / Ukuran Kontras (Kecil vs Besar)": (
        "Rivalry / Scale Contrast: Tiny bold object vs giant calm obstacle, or two contrasting "
        "objects competing where the calmer one wins effortlessly."
    ),
    "Karakter Diam Sinematik -> Twist Kocak di Akhir": (
        "Still Subject, Living World -> Comedic Twist: Start with moody cinematic stillness and "
        "dramatic slow camera push-in so viewers expect something epic, then break the tension "
        "with an absurd micro-reaction or unexpected comedic twist in the final seconds."
    ),
}

BG_OPTIONS = {
    "Otomatis Sesuai Objek (Paling Natural)": "Choose the most natural, visually clean real-world setting that fits the object.",
    "Meja Kayu Hangat Cahaya Pagi": "warm sunlit wooden table with soft morning bokeh",
    "Meja Dapur Bersih & Properti Harian": "clean kitchen countertop with everyday props in soft bokeh",
    "Meja Bengkel Rapi Cahaya Jendela": "clean workshop workbench with natural side window light",
    "Batu Taman Luar Ruangan & Bokeh Hijau": "outdoor garden stone surface with lush green bokeh",
    "Meja Kerja Minimalis Cahaya Siang": "minimalist study desk with soft natural daylight",
}

CLARIO_MODELS = [
    "clario/gemini-3.7-flash",
    "clario/claude-sonnet-4.6",
    "clario/gemini-3.7-flash-auto",
    "clario/gpt-5.6-sol",
    "clario/qwen3.8-flash",
    "clario/opus-5",
]


def compress_image_to_data_url(uploaded_file, max_side: int = 768, quality: int = 80):
    img = Image.open(uploaded_file)
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    raw_bytes = buf.getvalue()
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}", round(len(raw_bytes) / 1024, 1), img


def build_system_prompt(locked_name: str, lock_shape: bool, safe_rules: bool) -> str:
    if locked_name:
        lock_rule = (
            f'MANDATORY SUBJECT LOCK: The user explicitly specified the exact subject is "{locked_name}". '
            f'You MUST use ONLY "{locked_name}" as the main character. NEVER substitute it with an apple, '
            "fruit, human, baby, or any other unrelated object."
        )
    elif lock_shape:
        lock_rule = (
            "STRICT SHAPE LOCK: Inspect the attached photo(s) carefully. Use ONLY the exact physical "
            "object(s) visible in the photo(s), preserving their exact silhouette, limbs, colors, and "
            "material texture. NEVER replace them with human figures, babies, or unrelated objects."
        )
    else:
        lock_rule = "Keep character appearance consistent throughout the clip."

    safe_rule = (
        "MONETIZATION SAFE: Even if the object is a lighter or tool, keep it 100% family-safe "
        "(no real open flames, no burning, no smoke, no cigarettes, no violence, no copyrighted logos, "
        "and ZERO on-screen text or subtitles inside the video)."
        if safe_rules
        else "Pure non-verbal visual storytelling with zero on-screen text."
    )

    return f"""You are an elite viral YouTube Shorts director specializing in high-CTR, high-retention, non-verbal 9:16 visual comedy using real physical toys or everyday objects.

{lock_rule}
{safe_rule}

Avoid boring, repetitive bouncing or generic wiggling. Design a sharp, genuinely funny 9-10 second scenario tailored specifically to THIS exact object using the 4-Phase Structure:
1. Phase 1 (0.0-1.5s) VISUAL HOOK (CTR / Stop Scroll): Start immediately in an unusual, eye-catching situation or bold scale contrast, tight close-up, clean framing.
2. Phase 2 (1.5-5.0s) EXPECTATION & TENSION (Retention): Establish a clear non-verbal goal or dead-serious buildup (slow zoom, tense pause) so viewers stay to see what happens.
3. Phase 3 (5.0-8.0s) TWIST / IRONY (Laughter): Break the expectation instantly with physical irony, deadpan failure, instant karma, or clever object-logic humor.
4. Phase 4 (8.0-10.0s) REPLAY TRIGGER (Loop / Rewatch): Deliver a fast blink-and-miss micro-reaction or clever visual snap that seamlessly loops or compels viewers to rewatch.

Return ONLY valid JSON (no markdown fences, no extra text) with these exact keys:
{{
  "detected_object": "Exact English name and concise visual description of the subject",
  "story_breakdown_id": "Penjelasan singkat Bahasa Indonesia untuk 4 fase:\\n• 0–1.5d (Hook): ...\\n• 1.5–5d (Ekspektasi): ...\\n• 5–8d (Twist Tawa): ...\\n• 8–10d (Replay/Loop): ...",
  "video_prompt_en": "One single, production-ready English prompt for 9:16 vertical AI video generation (Google Flow Ingredients mode) preserving the exact object shape/colors/texture (do not freeze raw photo background), clearly detailing camera movement, lighting, setting, all 4 timed beats, and zero text/flames/smoke.",
  "seo_pack_en": "3 high-CTR global Tier-1 English Shorts title options (under 55 chars each), followed by a 1-sentence punchy English description and 8 relevant global hashtags."
}}"""


def parse_json_safely(raw_text: str):
    cleaned = str(raw_text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        cleaned = cleaned[first : last + 1]
    return json.loads(cleaned)


def call_clariohub(
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_data_urls: list,
    temperature: float,
):
    content = [{"type": "text", "text": user_text}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "max_tokens": 1000,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")

    envelope = resp.json()
    msg_content = envelope.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(msg_content, list):
        msg_content = "\n".join(part.get("text", "") for part in msg_content if isinstance(part, dict))
    return str(msg_content).strip()


# --- Sidebar: Konfigurasi ClarioHub ---
with st.sidebar:
    st.header("⚙️ Konfigurasi ClarioHub")
    default_secret_key = ""
    try:
        default_secret_key = st.secrets.get("CLARIOHUB_API_KEY", "")
    except Exception:
        default_secret_key = ""

    api_key_input = st.text_input(
        "ClarioHub API Key (sk-clario-...)",
        value=default_secret_key,
        type="password",
        placeholder="sk-clario-...",
        help="Bisa disimpan permanen di Streamlit Secrets dengan nama CLARIOHUB_API_KEY.",
    )
    endpoint_url = st.text_input(
        "Endpoint URL",
        value="https://api.clariohub.id/v1/chat/completions",
    )
    selected_model = st.selectbox("Model ClarioHub", CLARIO_MODELS, index=0)
    custom_model = st.text_input(
        "ID Model Manual (Opsional)",
        placeholder="Kosongkan jika pakai pilihan di atas",
    )
    active_model = custom_model.strip() or selected_model
    st.caption(f"Model aktif: `{active_model}`")

# --- Main Header ---
st.title("🎬 ClarioHub 4-Phase Viral Shorts Studio")
st.caption("Backend Python Stabil • Auto-Kompres Foto • Kunci Nama Objek • Alur 4 Fase CTR & Replay")

# --- Input Bahan & Pengaturan ---
locked_object_name = st.text_input(
    "🔒 Kunci Nama Objek Asli (Sangat Disarankan — Anti Salah Karakter)",
    placeholder="Contoh: korek api gas plastik bening biru / belalang mainan hijau / sendok besi",
)

uploaded_files = st.file_uploader(
    "📷 Upload 1–4 Foto Bahan Asli (Ingredients)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

processed_images = []
if uploaded_files:
    cols = st.columns(min(len(uploaded_files[:4]), 4))
    for idx, f in enumerate(uploaded_files[:4]):
        data_url, kb, preview_img = compress_image_to_data_url(f)
        processed_images.append(data_url)
        with cols[idx]:
            st.image(preview_img, caption=f"Bahan #{idx + 1} ({kb} KB)", use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    comedy_style = st.selectbox("🎭 Gaya Cerita & Komedi", list(STYLE_GUIDES.keys()))
with col2:
    bg_label = st.selectbox("🖼️ Latar / Setting", list(BG_OPTIONS.keys()))

col_c1, col_c2 = st.columns(2)
with col_c1:
    lock_shape = st.checkbox("Kunci bentuk asli sesuai foto/nama", value=True)
with col_c2:
    safe_rules = st.checkbox("Aman monetisasi (tanpa api/asap/teks)", value=True)

user_idea_note = st.text_input(
    "💡 Catatan / Twist Tambahan (Opsional)",
    placeholder="Contoh: koreknya sok berani tapi pas ditekan malah kaget sendiri",
)

btn_col1, btn_col2 = st.columns(2)
with btn_col1:
    run_normal = st.button("🚀 Rancang Skenario 4 Fase + SEO", type="primary")
with btn_col2:
    run_fresh = st.button("🔄 Buat Ide Lain (Anti-Monoton)")

if run_normal or run_fresh:
    if not api_key_input.strip():
        st.error("Masukkan ClarioHub API Key (`sk-clario-...`) di menu Sidebar sebelah kiri dulu.")
    elif not processed_images and not locked_object_name.strip():
        st.warning("Isi kolom **Kunci Nama Objek Asli** atau upload minimal 1 foto bahan dulu.")
    else:
        is_fresh = bool(run_fresh)
        st.session_state.variation_count = (st.session_state.variation_count + 1) if is_fresh else 1

        avoid_block = ""
        if is_fresh and st.session_state.previous_ideas:
            avoid_list = "\n".join(f"- {idea}" for idea in st.session_state.previous_ideas[-4:])
            avoid_block = f"\nDO NOT REPEAT these previous gags:\n{avoid_list}"

        user_prompt_parts = [
            (
                f"EXACT SUBJECT (DO NOT CHANGE): {locked_object_name.strip()}"
                if locked_object_name.strip()
                else "Identify the exact physical subject strictly from the attached photo(s)."
            ),
            f"Style direction: {STYLE_GUIDES[comedy_style]}",
            f"Background: {BG_OPTIONS[bg_label]}",
            f"User custom note: {user_idea_note.strip()}" if user_idea_note.strip() else "",
            (
                f"Variation #{st.session_state.variation_count}-{int(time.time())}: "
                "Invent a completely fresh gag, prop interaction, and comedic twist."
                if is_fresh
                else ""
            ),
            avoid_block,
        ]
        user_text = "\n".join(p for p in user_prompt_parts if p)

        with st.spinner(f"Merancang skenario 4 fase lewat {active_model}..."):
            try:
                raw_out = call_clariohub(
                    endpoint=endpoint_url.strip(),
                    api_key=api_key_input.strip(),
                    model=active_model,
                    system_prompt=build_system_prompt(locked_object_name.strip(), lock_shape, safe_rules),
                    user_text=user_text,
                    image_data_urls=processed_images,
                    temperature=0.95 if is_fresh else 0.72,
                )
                try:
                    parsed = parse_json_safely(raw_out)
                    st.session_state.last_result = {
                        "detected_object": parsed.get("detected_object", locked_object_name.strip() or "Terbaca"),
                        "story_breakdown_id": parsed.get("story_breakdown_id", ""),
                        "video_prompt_en": parsed.get("video_prompt_en", ""),
                        "seo_pack_en": parsed.get("seo_pack_en", ""),
                    }
                    short_summary = parsed.get("story_breakdown_id", "").splitlines()[0][:120]
                    if short_summary:
                        st.session_state.previous_ideas.append(short_summary)
                except Exception:
                    st.session_state.last_result = {
                        "detected_object": locked_object_name.strip() or "Format teks bebas",
                        "story_breakdown_id": "Model mengembalikan teks langsung (bukan JSON). Lihat hasilnya di kotak Prompt Video di bawah.",
                        "video_prompt_en": raw_out,
                        "seo_pack_en": "",
                    }
            except Exception as exc:
                st.error(f"Gagal memanggil ClarioHub API: {exc}")

# --- Output Display ---
if st.session_state.last_result:
    res = st.session_state.last_result
    st.divider()
    st.subheader("1️⃣ Bedah Skenario 4 Fase (Cek Sebelum Render)")
    st.info(f"**Objek yang Dipakai:** {res['detected_object']}")
    st.markdown(f"<div class='phase-card'>{res['story_breakdown_id']}</div>", unsafe_allow_html=True)

    st.subheader("2️⃣ Prompt Video Final (Siap Tempel ke Flow)")
    st.caption("Ketuk ikon salin (Copy) di pojok kanan atas kotak di bawah ini:")
    st.code(res["video_prompt_en"], language=None)

    if res["seo_pack_en"]:
        st.subheader("3️⃣ Paket SEO CTR Tinggi (Global Tier-1)")
        st.code(res["seo_pack_en"], language=None)
