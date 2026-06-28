import os
import json
import base64
from flask import Flask, request, Response
from groq import Groq
import requests

app = Flask(__name__)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "YOUR_GROQ_API_KEY_LOCAL_FALLBACK")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "YOUR_DEEPGRAM_API_KEY_LOCAL_FALLBACK")

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = (
    "You are a friendly, highly professional Indian female AI medical receptionist for City Hospital. "
    "Your objective is to collect appointment details from patients step-by-step: "
    "1. Patient's Name, 2. Medical Department/Doctor needed, 3. Preferred Date and Time. "
    "CRITICAL: Dynamically respond in the language or script chosen by the user. If they speak in English, reply in English. "
    "If they speak in Hindi, reply in Hindi script. If they speak in Hinglish, reply in Hinglish. "
    "Keep responses incredibly brief (strictly 1 to 2 sentences max) so the phone call flows without lag."
)

def generate_phone_voice(text_data):
    """Hits Deepgram's cloud engine to convert text into telephonic 8kHz Mu-law streams."""
    model = "aura-asteria-en"
    if any("\u0900" <= char <= "\u097F" for char in text_data):
        model = "aura-amira-hi"
        
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
    except Exception as e:
        print(f"Voice generation exception: {e}")
    return None

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly by Twilio when a patient dials the hospital line."""
    host = request.host
    xml_data = f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="wss://{host}/media-stream" /></Connect></Response>'
    return Response(xml_data, mimetype='text/xml')

def handle_websocket(ws):
    """Handles the live raw audio data stream entirely outside of Flask's routing maps."""
    print("🚀 SUCCESS: Connected to Twilio Audio WebSocket Pipeline!")
    stream_sid = None
    call_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    while not ws.closed:
        message = ws.receive()
        if message is None:
            continue
            
        data = json.loads(message)
        
        if data['event'] == "start":
            stream_sid = data['start']['streamSid']
            print(f"Connected to Live Call Streaming Session ID: {stream_sid}")
            
            initial_greeting = "Welcome to City Hospital. सिटी हॉस्पिटल में आपका स्वागत है। How can I help you today?"
            audio_payload = generate_phone_voice(initial_greeting)
            if audio_payload and stream_sid:
                ws.send(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": audio_payload}
                }))
            call_history.append({"role": "assistant", "content": initial_greeting})
            
        elif data['event'] == "media":
            print("🎙️ Receiving live raw audio frame...")
            
            # Temporary context placeholder for simulator
            patient_speech_text = "Hello, look for an eye appointment" 
            call_history.append({"role": "user", "content": patient_speech_text})
            
            try:
                chat_completion = groq_client.chat.completions.create(
                    messages=call_history,
                    model="llama-3.3-70b-versatile",
                )
                ai_response = chat_completion.choices[0].message.content
                call_history.append({"role": "assistant", "content": ai_response})
                
                audio_payload = generate_phone_voice(ai_response)
                if audio_payload and stream_sid:
                    ws.send(json.dumps({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": audio_payload}
                    }))
            except Exception as e:
                print(f"Processing loop execution halt: {e}")
                
        elif data['event'] == "stop":
            print("Call terminated.")
            break

# --- DISPATCHER MIDDLEWARE ---
# This bypasses Flask entirely for the websocket route, routing it right to the handler function
class NativeWebSocketDispatcher(object):
    def __init__(self, flask_app):
        self.flask_app = flask_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path == '/media-stream':
            # Safely extract the active websocket connection from environment context
            ws = environ.get('wsgi.websocket')
            if ws:
                handle_websocket(ws)
                return []
        return self.flask_app(environ, start_response)

if __name__ == "__main__":
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    
    # Wrap our app inside the direct pipeline interceptor
    dispatcher_wrapped_app = NativeWebSocketDispatcher(app)
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting server on port {port}...")
    server = pywsgi.WSGIServer(('0.0.0.0', port), dispatcher_wrapped_app, handler_class=WebSocketHandler)
    server.serve_forever()
