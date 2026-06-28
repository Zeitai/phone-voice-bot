import os
from flask import Flask, request, Response
from groq import Groq

app = Flask(__name__)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = (
    "You are a friendly, professional Indian female AI medical receptionist for City Hospital. "
    "Collect appointment details step-by-step: 1. Name, 2. Department, 3. Date/Time. "
    "Respond in the language chosen by the user (English, Hindi, or Hinglish). "
    "Keep answers strictly 1 to 2 sentences max. Do not add any ambient markdown text."
)

# Shared memory log to keep track of conversations by phone number
call_logs = {}

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly when a patient dials the hospital line."""
    from_number = request.form.get("From", "unknown")
    
    # Initialize a clean history for this call session
    call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    greeting = "Welcome to City Hospital. How can I help you today?"
    call_logs[from_number].append({"role": "assistant", "content": greeting})
    
    # Twilio's standard <Gather> engine captures voice inputs, handles audio noise automatically,
    # and converts it to text before hitting our server loop.
    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say voice="Polly.Aditi" language="en-IN">{greeting}</Say>
        <Gather input="speech" action="/handle-response" speechTimeout="auto" hints="appointment, doctor, hospital, Hindi" />
    </Response>"""
    return Response(xml_data, mimetype='text/xml')

@app.route("/handle-response", methods=['POST'])
def handle_response():
    """Processes incoming transcribed text inputs seamlessly without static stream interruptions."""
    from_number = request.form.get("From", "unknown")
    user_speech = request.form.get("SpeechResult", "")
    
    # Fallback if Twilio didn't catch any speech clearly
    if not user_speech:
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Aditi" language="en-IN">I'm sorry, I didn't quite catch that. Could you please repeat?</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
        return Response(xml_data, mimetype='text/xml')
        
    # Retrieve active session history context
    if from_number not in call_logs:
        call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    print(f"🗣️ User Said: {user_speech}")
    call_logs[from_number].append({"role": "user", "content": user_speech})
    
    try:
        # Generate pristine response via Groq
        completion = groq_client.chat.completions.create(
            messages=call_logs[from_number], model="llama-3.3-70b-versatile"
        )
        ai_response = completion.choices[0].message.content
        print(f"🤖 AI Response: {ai_response}")
        call_logs[from_number].append({"role": "assistant", "content": ai_response})
        
        # Match language profile rendering for output voice synthesis routing
        voice_profile = 'voice="Polly.Aditi" language="en-IN"'
        if any("\u0900" <= char <= "\u097F" for char in ai_response):
            voice_profile = 'voice="Polly.Madhav" language="hi-IN"'
            
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say {voice_profile}>{ai_response}</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
    except Exception as e:
        print(f"Loop error execution halt: {e}")
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Aditi" language="en-IN">An internal technical connection issue occurred. Please standby.</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
