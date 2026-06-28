import os
import json
import base64
import asyncio
import threading
import websockets
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
    """Converts AI responses into 8kHz Mu-law telephony audio streams."""
    model = "aura-asteria-en"
    if any("\u0900" <= char <= "\u097F" for char in text_data):
        model = "aura-amira-hi"  # Shift to native Hindi voice model
        
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
    """Twilio routing entry point."""
    host = request.host
    xml_data = f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="wss://{host}/media-stream" /></Connect></Response>'
    return Response(xml_data, mimetype='text/xml')

async def dg_stream_handler(ws, stream_sid, call_history):
    """Maintains a dedicated live streaming connection to Deepgram's STT engine."""
    dg_url = "wss://api.deepgram.com/v1/listen?model=nova-2-medical&encoding=mulaw&sample_rate=8000&endpointing=300"
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    
    async with websockets.connect(dg_url, extra_headers=headers) as dg_ws:
        async def receive_from_deepgram():
            async for msg in dg_ws:
                response = json.loads(msg)
                transcript = response.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                
                if transcript.strip() and response.get("is_final"):
                    print(f"🗣️ Transcribed Voice: {transcript}")
                    call_history.append({"role": "user", "content": transcript})
                    
                    # Call Groq safely inside the async flow
                    completion = groq_client.chat.completions.create(
                        messages=call_history, model="llama-3.3-70b-versatile"
                    )
                    ai_text = completion.choices[0].message.content
                    print(f"🤖 AI Reply: {ai_text}")
                    call_history.append({"role": "assistant", "content": ai_text})
                    
                    audio_payload = generate_phone_voice(ai_text)
                    if audio_payload:
                        ws.send(json.dumps({
                            "event": "media", "streamSid": stream_sid,
                            "media": {"payload": audio_payload}
                        }))

        async def send_to_deepgram():
            while not ws.closed:
                try:
                    message = ws.receive()
                    if message is None: break
                    data = json.loads(message)
                    
                    if data['event'] == "media":
                        payload = data['media']['payload']
                        await dg_ws.send(json.dumps({"chunky_demux_stream": payload}))
                    elif data['event'] == "stop":
                        break
                except Exception:
                    break

        await asyncio.gather(receive_from_deepgram(), send_to_deepgram())

def start_async_loop(ws, stream_sid, call_history):
    """Creates a completely isolated thread safety loop for the audio data runtime."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dg_stream_handler(ws, stream_sid, call_history))
    loop.close()

def handle_websocket(ws):
    """Intercepts Twilio traffic and boots the background loop thread smoothly."""
    print("🚀 Connected to Twilio Audio Pipeline!")
    stream_sid = None
    call_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    message = ws.receive()
    if message:
        data = json.loads(message)
        if data['event'] == "start":
            stream_sid = data['start']['streamSid']
            greeting = "Welcome to City Hospital. How can I help you today?"
            audio_payload = generate_phone_voice(greeting)
            if audio_payload:
                ws.send(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": audio_payload}}))
            call_history.append({"role": "assistant", "content": greeting})
            
            # Spin up the async engine on a separate background thread to bypass gevent lockups
            t = threading.Thread(target=start_async_loop, args=(ws, stream_sid, call_history))
            t.daemon = True
            t.start()

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
