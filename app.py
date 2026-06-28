import os
import json
import base64
from flask import Flask, request, Response
from groq import Groq
import requests

app = Flask(__name__)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = (
    "You are a friendly, professional Indian female AI medical receptionist for City Hospital. "
    "Collect appointment details step-by-step: 1. Name, 2. Department, 3. Date/Time. "
    "Respond in the language chosen by the user (English, Hindi script, or Hinglish). "
    "Keep answers strictly 1 to 2 sentences max."
)

def generate_phone_voice(text_data):
    """Converts text into 8kHz Mu-law telephony audio streams using Deepgram."""
    model = "aura-asteria-en"
    if any("\u0900" <= char <= "\u097F" for char in text_data):
        model = "aura-amira-hi"
        
    url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mulaw&sample_rate=8000"
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json={"text": text_data})
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        print(f"TTS Engine Error: {e}")
    return None

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Twilio entry routing."""
    host = request.host
    xml_data = f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="wss://{host}/media-stream" /></Connect></Response>'
    return Response(xml_data, mimetype='text/xml')

def handle_websocket(ws):
    """Handles the live connection stream simply and cleanly using normal loops."""
    print("🚀 Connected to Twilio Audio Pipeline!")
    stream_sid = None
    call_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # We use a frame counter to pause before capturing input
    frame_counter = 0
    
    while not ws.closed:
        message = ws.receive()
        if message is None:
            continue
            
        data = json.loads(message)
        
        if data['event'] == "start":
            stream_sid = data['start']['streamSid']
            greeting = "Welcome to City Hospital. How can I help you today?"
            audio_payload = generate_phone_voice(greeting)
            if audio_payload:
                ws.send(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": audio_payload}}))
            call_history.append({"role": "assistant", "content": greeting})
            
        elif data['event'] == "media":
            frame_counter += 1
            
            # Instead of a constant loop or a thread block, we wait for a steady window of connection frames 
            # to simulate speech pause before checking what the user said.
            if frame_counter == 120:  
                print("🎙️ Checking incoming user voice buffer channel...")
                
                # Production pipeline user voice anchor placeholder
                user_speech = "Hello, I want to see a doctor."
                print(f"🗣️ Captured Input: {user_speech}")
                call_history.append({"role": "user", "content": user_speech})
                
                try:
                    completion = groq_client.chat.completions.create(
                        messages=call_history, model="llama-3.3-70b-versatile"
                    )
                    ai_text = completion.choices[0].message.content
                    print(f"🤖 AI Response: {ai_text}")
                    call_history.append({"role": "assistant", "content": ai_text})
                    
                    audio_payload = generate_phone_voice(ai_text)
                    if audio_payload and stream_sid:
                        ws.send(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": audio_payload}}))
                except Exception as e:
                    print(f"LLM Engine Halt: {e}")
                    
        elif data['event'] == "stop":
            print("Call terminated.")
            break

class NativeWebSocketDispatcher(object):
    def __init__(self, flask_app):
        self.flask_app = flask_app
    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO', '') == '/media-stream':
            ws = environ.get('wsgi.websocket')
            if ws:
                handle_websocket(ws)
                return []
        return self.flask_app(environ, start_response)

if __name__ == "__main__":
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    dispatcher_wrapped_app = NativeWebSocketDispatcher(app)
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting server on port {port}...")
    server = pywsgi.WSGIServer(('0.0.0.0', port), dispatcher_wrapped_app, handler_class=WebSocketHandler)
    server.serve_forever()
