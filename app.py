import os
import uuid
from flask import Flask, request, Response, send_file
from flask_cors import CORS
from groq import Groq
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# --- SECURE MULTI-API CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") # Ensure this is set in Render env

groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Folder to temporarily cache premium soothing audio files
AUDIO_CACHE_DIR = "static_audio"
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# --- GLOBAL RECEPTIONIST SYSTEM INSTRUCTIONS ---
SYSTEM_PROMPT = (
    "You are a highly professional, polite, and reassuring female AI Receptionist for City Hospital. "
    "Your primary objective is to assist English-speaking patients from the US, UK, and Canada. "
    "Interact with the patient with absolute respect, empathy, and corporate standard clarity. "
    "Efficiently collect the patient's name, their medical concern or requested department, and their preferred appointment time one by one. "
    "Keep your responses concise, clear, and professional (strictly 1 to 2 sentences max). Avoid complex jargon. "
    "CRITICAL BUSINESS RULE: As soon as the patient provides their name, medical concern, and appointment time, you must state: "
    "'Your appointment has been successfully booked. Thank you for calling City Hospital.' "
    "Immediately append the exact token '[CALL_END]' at the very end of your response so the telephony server knows to hang up."
)

call_logs = {}

def generate_soothing_audio(text_content):
    """Generates ultra-clear crisp audio using OpenAI's high-fidelity TTS engine."""
    try:
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(AUDIO_CACHE_DIR, filename)
        
        # Using 'shimmer' voice - highly professional, clear, crisp, and soothing
        response = openai_client.audio.speech.create(
            model="tts-1",
            voice="shimmer", 
            input=text_content
        )
        response.stream_to_file(filepath)
        return filename
    except Exception as e:
        print(f"Audio Generation Error: {e}")
        return None

@app.route("/static_audio/<filename>")
def serve_audio(filename):
    """Serves the generated premium audio file to Twilio instantly."""
    return send_file(os.path.join(AUDIO_CACHE_DIR, filename), mimetype="audio/mpeg")

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly when a patient dials the hospital line."""
    from_number = request.form.get("From", "unknown")
    base_url = request.url_root.rstrip('/')
    
    call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    greeting = "Welcome to City Hospital. How may I assist with your appointment scheduling today?"
    call_logs[from_number].append({"role": "assistant", "content": greeting})
    
    # Generate the soothing audio stream
    audio_file = generate_soothing_audio(greeting)
    
    if audio_file:
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{base_url}/static_audio/{audio_file}</Play>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
    else:
        # Fallback if OpenAI fails
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">{greeting}</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

@app.route("/handle-response", methods=['POST'])
def handle_response():
    """Processes incoming speech and plays the premium dynamic voice response."""
    from_number = request.form.get("From", "unknown")
    user_speech = request.form.get("SpeechResult", "")
    base_url = request.url_root.rstrip('/')
    
    if not user_speech:
        fail_text = "I am sorry, I did not catch that. Could you please repeat it?"
        audio_file = generate_soothing_audio(fail_text)
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{base_url}/static_audio/{audio_file}</Play>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
        return Response(xml_data, mimetype='text/xml')
        
    if from_number not in call_logs:
        call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    print(f"🗣️ User Said: {user_speech}")
    call_logs[from_number].append({"role": "user", "content": user_speech})
    
    try:
        completion = groq_client.chat.completions.create(
            messages=call_logs[from_number], 
            model="llama-3.1-8b-instant"
        )
        ai_response = completion.choices[0].message.content
        print(f"🤖 AI Response: {ai_response}")
        
        if "[CALL_END]" in ai_response:
            clean_response = ai_response.replace("[CALL_END]", "").strip()
            audio_file = generate_soothing_audio(clean_response)
            
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Play>{base_url}/static_audio/{audio_file}</Play>
                <Hangup/>
            </Response>"""
            if from_number in call_logs:
                del call_logs[from_number]
        else:
            call_logs[from_number].append({"role": "assistant", "content": ai_response})
            audio_file = generate_soothing_audio(ai_response)
            
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Play>{base_url}/static_audio/{audio_file}</Play>
                <Gather input="speech" action="/handle-response" speechTimeout="4" />
            </Response>"""
            
    except Exception as e:
        print(f"Error: {e}")
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">We are experiencing technical difficulties. Please try again shortly.</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
