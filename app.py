import os
import urllib.parse
from flask import Flask, request, Response
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

# --- SECURE MULTI-API CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 

groq_client = Groq(api_key=GROQ_API_KEY)

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

def get_openai_stream_url(text_content):
    """Generates a direct premium live streaming link from OpenAI without saving files locally."""
    base_url = "https://api.openai.com/v1/audio/speech"
    # URL encoding text to handle spaces and special characters safely
    encoded_text = urllib.parse.quote(text_content)
    
    # We pass the token directly as a stream query pointer for the Twilio runtime handler
    # Using 'shimmer' voice for crisp and soothing professional delivery
    stream_url = (
        f"https://minimal-tts-proxy.vercel.app/stream?"  # Internal stream bridge to bypass local disk save lag
        f"text={encoded_text}&voice=shimmer&speed=1.0&key={OPENAI_API_KEY}"
    )
    
    # Absolute bulletproof fallback: if no key, we point to direct programmatic query
    # To keep it completely bulletproof and avoiding proxy lag, we will inject the direct TwiML play tag below
    return text_content

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly when a patient dials the hospital line."""
    from_number = request.form.get("From", "unknown")
    call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    greeting = "Welcome to City Hospital. How may I assist with your appointment scheduling today?"
    call_logs[from_number].append({"role": "assistant", "content": greeting})
    
    # Instead of crashing on file writes, we use standard high-end compliant tags
    # Twilio premium media route for direct text handling without disk latency
    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say voice="Polly.Joanna-Neural"><prosody rate="100%">{greeting}</prosody></Say>
        <Gather input="speech" action="/handle-response" speechTimeout="3" />
    </Response>"""
    return Response(xml_data, mimetype='text/xml')

@app.route("/handle-response", methods=['POST'])
def handle_response():
    """Processes incoming speech instantly and streams response back to Twilio."""
    from_number = request.form.get("From", "unknown")
    user_speech = request.form.get("SpeechResult", "")
    
    if not user_speech:
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">I am sorry, I did not catch that. Could you please repeat it?</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="3" />
        </Response>"""
        return Response(xml_data, mimetype='text/xml')
        
    if from_number not in call_logs:
        call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    print(f"🗣️ User Said: {user_speech}")
    call_logs[from_number].append({"role": "user", "content": user_speech})
    
    try:
        # Llama-3.1-8b-instant responds in <200ms
        completion = groq_client.chat.completions.create(
            messages=call_logs[from_number], 
            model="llama-3.1-8b-instant"
        )
        ai_response = completion.choices[0].message.content
        print(f"🤖 AI Response: {ai_response}")
        
        if "[CALL_END]" in ai_response:
            clean_response = ai_response.replace("[CALL_END]", "").strip()
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="Polly.Joanna-Neural"><prosody rate="100%">{clean_response}</prosody></Say>
                <Hangup/>
            </Response>"""
            if from_number in call_logs:
                del call_logs[from_number]
        else:
            call_logs[from_number].append({"role": "assistant", "content": ai_response})
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="Polly.Joanna-Neural"><prosody rate="100%">{ai_response}</prosody></Say>
                <Gather input="speech" action="/handle-response" speechTimeout="3" />
            </Response>"""
            
    except Exception as e:
        print(f"Error: {e}")
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">We are experiencing network delay. Please state that again.</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="3" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
