
import os
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def upload_to_imgbb(image_bytes):
    API_KEY = os.getenv("IMGBB_API_KEY")
    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": API_KEY},
        files={"image": image_bytes}
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

                prompt = f"""
                The user has the following skin details:
                Skin Tone: {skin_tone}
                Undertone: {undertone}
                Skin Type: {skin_type}

                Based on these, recommend 3 real foundation and 3 concealer products.
                Each recommendation must include:
                - Brand + product name + exact shade
                - One-line reason why it's a good match

                Concealers should be 1-2 shades lighter. Undertones and formula must match.
                Reply strictly in this JSON format:
                {{
                "skin_tone_detected": "",
                "undertone_detected": "",
                "skin_type_detected": "",
                "recommended_foundations": [
                    {{"product": "", "reason": ""}},
                    {{"product": "", "reason": ""}},
                    {{"product": "", "reason": ""}}
                ],
                "recommended_concealers": [
                    {{"product": "", "reason": ""}},
                    {{"product": "", "reason": ""}},
                    {{"product": "", "reason": ""}}
                ]
                }}
                """

                completion = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "You are a professional beauty assistant."},
                        {"role": "user", "content": prompt}
                    ]
                )

                raw_result = completion.choices[0].message.content.strip()

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
                                "Concealers must be 1-2 shades lighter than the foundation. "
                                "Undertone must match. "
                                "Return only valid strict JSON in this format: "
                                "{"
                                "\"skin_tone_detected\": \"\", "
                                "\"undertone_detected\": \"\", "
                                "\"skin_type_detected\": \"\", "
                                "\"recommended_foundations\": ["
                                "{\"product\": \"\", \"reason\": \"\"},"
                                "{\"product\": \"\", \"reason\": \"\"},"
                                "{\"product\": \"\", \"reason\": \"\"}"
                                "], "
                                "\"recommended_concealers\": ["
                                "{\"product\": \"\", \"reason\": \"\"},"
                                "{\"product\": \"\", \"reason\": \"\"},"
                                "{\"product\": \"\", \"reason\": \"\"}"
                                "]"
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

            # Try parsing the JSON safely
            try:
                recommendation = json.loads(raw_result)
            except json.JSONDecodeError:
                json_start = raw_result.find('{')
                json_end = raw_result.rfind('}')
                if json_start != -1 and json_end != -1:
                    cleaned_json = raw_result[json_start:json_end+1]
                    recommendation = json.loads(cleaned_json)
                else:
                    flash("Could not parse AI response.")
                    recommendation = None

        except Exception as e:
            flash(str(e))

    return render_template('index.html', recommendation=recommendation, raw_result=raw_result)

if __name__ == '__main__':
    app.run(debug=True)
