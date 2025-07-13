import os
import json
import requests
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv
import base64

# تحميل المتغيرات
load_dotenv()

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# تحميل قاعدة بيانات المنتجات
shades_df = pd.read_csv("data/allShades.csv")
shades_df.columns = shades_df.columns.str.strip()
shades_df["description"] = shades_df["description"].astype(str)

# توصيات دقيقة بناءً على lightness و undertone
import colorsys

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4))  # Normalized 0-1

def color_distance(rgb1, rgb2):
    return sum((a - b) ** 2 for a, b in zip(rgb1, rgb2))  # Euclidean distance

def recommend_foundations_precise(skin_tone, undertone, skin_color_hex=None, max_results=5):
    target_lightness_map = {
        "Light": 0.90,
        "Medium": 0.72,
        "Medium-dark": 0.53,
        "Dark": 0.30
    }

    undertone_map = {
        "Cool": ["cool", "pink", "rosy"],
        "Neutral": ["neutral", "olive"],
        "Warm": ["warm", "golden", "yellow", "peach"]
    }

    target_l = target_lightness_map.get(skin_tone, 0.5)
    undertone_keywords = undertone_map.get(undertone, [])

    filtered = shades_df[
        shades_df["description"].str.contains('|'.join(undertone_keywords), case=False, na=False)
    ].copy()

    filtered["tone_diff"] = abs(filtered["lightness"] - target_l)

    if skin_color_hex:
        try:
            user_rgb = hex_to_rgb(skin_color_hex)
            filtered["hex_diff"] = filtered["hex"].apply(lambda x: color_distance(user_rgb, hex_to_rgb(x)))
        except:
            filtered["hex_diff"] = 0.5  # default distance if failed
    else:
        filtered["hex_diff"] = 0.5

    # ترتيب حسب tone أولاً ثم hex_diff
    filtered = filtered.sort_values(by=["tone_diff", "hex_diff"])

    top = filtered[['brand', 'product', 'specific', 'description', 'imgSrc']].head(max_results)

    results = []
    for _, row in top.iterrows():
        results.append({
            "product": f"{row['brand']} - {row['product']} ({row['specific']})",
            "reason": row['description'],
            "imgSrc": row['imgSrc']
        })

    return results

# رفع صورة المستخدم إلى imgbb بطريقة صحيحة
def upload_to_imgbb(image_bytes):
    API_KEY = os.getenv("IMGBB_API_KEY")
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": API_KEY, "image": encoded_image}
    )
    if response.status_code == 200:
        return response.json()["data"]["url"]
    else:
        raise Exception(f"ImgBB upload failed: {response.status_code} - {response.text}")

@app.route('/', methods=['GET', 'POST'])
def index():
    recommendation = None
    raw_result = ""

    if request.method == 'POST':
        mode = request.form.get('mode')

        try:
            if mode == 'manual':
                skin_tone = request.form.get('skin_tone')
                undertone = request.form.get('undertone')
                skin_type = request.form.get('skin_type')
                skin_color_hex = None  # لا يوجد HEX في الوضع اليدوي

            else:
                uploaded_file = request.files.get('image')
                if not uploaded_file or uploaded_file.filename == '':
                    flash("Please upload a selfie.")
                    return redirect(request.url)

                filename = secure_filename(uploaded_file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                uploaded_file.save(filepath)

                with open(filepath, "rb") as f:
                    image_bytes = f.read()

                image_url = upload_to_imgbb(image_bytes)

                # برومبت التحليل
                completion = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages = [
                        {
                            "role": "system",
                            "content": ("You are a professional AI beauty assist ant. "
                                "You will analyze the user's selfie to detect their skin tone, undertone, and skin type. "
                                "Then you will recommend 3 real foundation products and 3 real concealer products based on that analysis. "
                                "Each product must include: brand name, product name, shade, and a short reason. "
                                "Return only strict JSON with no explanation. Format:\n"
                                "{"
                                "\"skin_tone_detected\": \"\", "
                                "\"undertone_detected\": \"\", "
                                "\"skin_type_detected\": \"\", "
                                "\"skin_color_hex\": \"\", "
                                "\"recommended_foundations\": [], "
                                "\"recommended_concealers\": []"
                                "}"
                            )
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Analyze this selfie and recommend foundation and concealer."},
                                {"type": "image_url", "image_url": {"url": image_url}}
                            ]
                        }
                    ]
                )

                raw_result = completion.choices[0].message.content.strip()
                json_start = raw_result.find("{")
                json_end = raw_result.rfind("}")
                cleaned_json = raw_result[json_start:json_end+1]
                parsed = json.loads(cleaned_json)

                skin_tone = parsed["skin_tone_detected"]
                undertone = parsed["undertone_detected"]
                skin_type = parsed["skin_type_detected"]
                skin_color_hex = parsed.get("skin_color_hex")

                # تطبيع التصنيفات
                tone_correction = {
                    "deep": "Dark",
                    "dark": "Dark",
                    "dark brown": "Dark",
                    "very dark": "Dark",
                    "medium dark": "Medium-dark",
                    "medium-dark": "Medium-dark",
                    "light-medium": "Medium",
                    "medium": "Medium",
                    "light": "Light",
                    "fair": "Light"
                }
                
                undertone_correction = {
                    "cool": "Cool",
                    "pink": "Cool",
                    "rosy": "Cool",
                    "neutral": "Neutral",
                    "olive": "Neutral",
                    "warm": "Warm",
                    "golden": "Warm",
                    "yellow": "Warm",
                    "peach": "Warm"
                }
                
                skin_tone = tone_correction.get(skin_tone.lower(), skin_tone)
                undertone = undertone_correction.get(undertone.lower(), undertone)

            # توصيات من قاعدة البيانات باستخدام lightness
            recommended = recommend_foundations_precise(skin_tone, undertone, skin_color_hex)

            recommendation = {
                "skin_tone_detected": skin_tone,
                "undertone_detected": undertone,
                "skin_type_detected": skin_type,
                "skin_color_hex": skin_color_hex,
                "recommended_foundations": recommended
            }

        except Exception as e:
            flash(str(e))

    return render_template('index.html', recommendation=recommendation, raw_result=raw_result)

if __name__ == '__main__':
    app.run(debug=True)