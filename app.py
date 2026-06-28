import os
import json
import base64
from flask import Flask, request, Response
from flask_sockets import Sockets
from groq import Groq
import requests

app = Flask(__name__)
sockets = Sockets(app)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_LOCAL_FALLBACK")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "YOUR_DEEPGRAM_API_KEY_LOCAL_FALLBACK")

groq_client = Groq(api_key=GROQ_API_KEY)

# SYSTEM PROMPT: Updated to allow dynamic language detection and switching
SYSTEM_PROMPT = (
    "You are a friendly, highly professional Indian female AI medical receptionist for City Hospital. "
    "Your objective is to collect appointment details from patients step-by-step: "
    "1. Patient's Name, 2. Medical Department/Doctor needed, 3. Preferred Date and Time. "
    "CRITICAL: Dynamically respond in the language or script chosen by the user. If they speak in English, reply in English. "
    "If they speak in Hindi, reply in Hindi script. If they speak in Hinglish, reply in Hinglish. "
    "Keep responses incredibly brief (strictly 1 to 2 sentences max) so the phone call flows without lag. "
    "Once all 3 details are collected, explicitly state that their appointment details are being processed."
)

def generate_phone_voice(text_data, language_code="en"):
    """
    Hits Deepgram's cloud engine to convert text into telephonic 8kHz Mu-law streams.
    Dynamically switches models depending on the language spoken.
    """
    # Default to English model
    model = "aura-asteria-en"
    
    # If the text contains Hindi Unicode characters, instantly switch to Deepgram's native Hindi voice
    if any("\u0900" <= char <= "\u097F" for char in text_data):
        model = "aura-amira-hi" # Deepgram's premium native Hindi voice profile
        
    url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mulaw&sample_rate=8000"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"text": text_data}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            print(f"Deepgram Voice Error: {response.text}")
            return None
    except Exception as e:
        print(f"Exception during Voice Call: {e}")
        return None

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly by Twilio when a patient dials the hospital line."""
    twiml_response = f"""
    <Response>
        <Connect>
            <Stream url="wss://{request.host}/media-stream" />
        </Connect>
    </Response>
    """
    return Response(twiml_response, mimetype='text/xml')

@sockets.route('/media-stream')
def media_stream(ws):
    """Maintains the live 2-way audio stream with the patient's phone carrier line."""
    print("Multilingual Hospital Call Session Started.")
    stream_sid = None
    
    # In-memory session tracking for conversation history
    call_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while not ws.closed:
        message = ws.receive()
        if message is None:
            continue
            
        data = json.loads(message)
        
        if data['event'] == "start":
            stream_sid = data['start']['streamSid']
            print(f"Live Call Streaming Active. ID: {stream_sid}")
            
            # Initial multi-language greeting welcoming all inputs
            initial_greeting = "Welcome to City Hospital. सिटी हॉस्पिटल में आपका स्वागत है। How can I help you today?"
            audio_payload = generate_phone_voice(initial_greeting)
            if audio_payload:
                ws.send(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": audio_payload}
                }))
            call_history.append({"role": "assistant", "content": initial_greeting})
            
        elif data['event'] == "media":
            patient_audio_payload = data['media']['payload']
            
            # [STT PIPELINE] -> Deepgram handles multilingual transcription automatically
            # Let's say a patient responds in pure English this time:
            patient_speech_text = "I want to book an appointment with a Cardiologist tomorrow at 10 AM." 
            print(f"Patient Said: {patient_speech_text}")
            
            call_history.append({"role": "user", "content": patient_speech_text})
            
            # Query Groq Llama 3.3 70B—it will automatically respond in English to match the user!
            try:
                chat_completion = groq_client.chat.completions.create(
                    messages=call_history,
                    model="llama-3.3-70b-versatile",
                )
                ai_response = chat_completion.choices[0].message.content
                print(f"Hospital AI Reply: {ai_response}")
                
                call_history.append({"role": "assistant", "content": ai_response})
                
                # Stream back the voice. Our function will auto-detect whether it needs to voice it in English or Hindi.
                audio_payload = generate_phone_voice(ai_response)
                
                if audio_payload and stream_sid:
                    media_back_to_phone = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": audio_payload}
                    }
                    ws.send(json.dumps(media_back_to_phone))
                        
            except Exception as e:
                print(f"Groq Engine Error: {e}")
                
        elif data['event'] == "stop":
            print("Patient disconnected.")
            break

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)