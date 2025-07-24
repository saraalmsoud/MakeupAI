import os
import json
import requests
from flask import Flask, render_template, request, redirect, flash
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv
import base64

load_dotenv()

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    image_url = None

    if request.method == 'POST':
        mode = request.form.get('mode')

        try:
            if mode == 'manual':
                skin_tone = request.form.get('skin_tone')
                undertone = request.form.get('undertone')
                skin_type = request.form.get('skin_type')

                recommendation = {
                    "skin_tone_detected": skin_tone,
                    "undertone_detected": undertone,
                    "skin_type_detected": skin_type,
                    "skin_color_hex": None,
                    "recommended_foundations": [],
                    "recommended_concealers": []
                }

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


                completion = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a professional AI beauty assistant. "
                                "You will analyze the user's selfie to detect their skin tone, undertone, and skin type. "
                                "Then you will recommend 3 real foundation products and 3 real concealer products based on that analysis. "
                                "Each product must include: brand name, product name, shade, and a short reason. "
                                "Return only strict JSON with no explanation. Format:\n"
                                "{"
                                "\\\"skin_tone_detected\\\": \\\"\\\", "
                                "\\\"undertone_detected\\\": \\\"\\\", "
                                "\\\"skin_type_detected\\\": \\\"\\\", "
                                "\\\"skin_color_hex\\\": \\\"\\\", "
                                "\\\"recommended_foundations\\\": [], "
                                "\\\"recommended_concealers\\\": []"
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

                parsed = json.loads(completion.choices[0].message.content)

                recommendation = {
                    "skin_tone_detected": parsed["skin_tone_detected"],
                    "undertone_detected": parsed["undertone_detected"],
                    "skin_type_detected": parsed["skin_type_detected"],
                    "skin_color_hex": parsed.get("skin_color_hex"),
                    "recommended_foundations": parsed.get("recommended_foundations", []),
                    "recommended_concealers": parsed.get("recommended_concealers", [])
                }

        except Exception as e:
            flash(str(e))

    return render_template('index.html', recommendation=recommendation, image_url=image_url)

if __name__ == '__main__':
    app.run(debug=True)
