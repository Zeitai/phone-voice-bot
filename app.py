import os
from flask import Flask, request, Response
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# --- GLOBAL COMMERCIAL RECEPTIONIST SYSTEM INSTRUCTIONS ---
SYSTEM_PROMPT = (
    "You are a highly professional, polite, and helpful female AI Receptionist for City Hospital. "
    "Your primary objective is to assist English-speaking patients from the US, UK, and Canada. "
    "Interact with the patient with absolute respect, empathy, and corporate standard clarity. "
    "Efficiently collect the patient's name, their medical concern or requested department, and their preferred appointment time one by one. "
    "Keep your responses concise, clear, and professional (strictly 1 to 2 sentences max). Avoid complex jargon or long explanations. "
    "CRITICAL BUSINESS RULE: As soon as the patient provides their name, medical concern, and appointment time, you must state: "
    "'Your appointment has been successfully booked. Thank you for calling City Hospital.' "
    "Immediately append the exact token '[CALL_END]' at the very end of your response so the telephony server knows to hang up."
)

# Active session tracking dictionary
call_logs = {}

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly when a patient dials the hospital line."""
    from_number = request.form.get("From", "unknown")
    
    # Initialize session history with the global English prompt
    call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Premium international warm greeting
    greeting = "Welcome to City Hospital. How may I assist with your appointment scheduling today?"
    call_logs[from_number].append({"role": "assistant", "content": greeting})
    
    # Integrated Premium US English Joanna Neural Engine with SSML for flawless cadence
    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say voice="Polly.Joanna-Neural">
            <prosody rate="98%">{greeting}</prosody>
        </Say>
        <Gather input="speech" action="/handle-response" speechTimeout="4" />
    </Response>"""
    return Response(xml_data, mimetype='text/xml')

@app.route("/handle-response", methods=['POST'])
def handle_response():
    """Processes incoming transcribed global text and dynamically routes with premium speech."""
    from_number = request.form.get("From", "unknown")
    user_speech = request.form.get("SpeechResult", "")
    
    if not user_speech:
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">I am sorry, I did not catch that. Could you please repeat it?</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
        return Response(xml_data, mimetype='text/xml')
        
    if from_number not in call_logs:
        call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    print(f"🗣️ User Said: {user_speech}")
    call_logs[from_number].append({"role": "user", "content": user_speech})
    
    try:
        # Optimized for ultra-fast conversational speeds using the instant framework
        completion = groq_client.chat.completions.create(
            messages=call_logs[from_number], 
            model="llama-3.1-8b-instant"
        )
        ai_response = completion.choices[0].message.content
        print(f"🤖 AI Response: {ai_response}")
        
        # Check if the AI determined the conversation is successfully finished
        if "[CALL_END]" in ai_response:
            clean_response = ai_response.replace("[CALL_END]", "").strip()
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="Polly.Joanna-Neural">
                    <prosody rate="98%">{clean_response}</prosody>
                </Say>
                <Hangup/>
            </Response>"""
            # Clear session logs to free server memory
            if from_number in call_logs:
                del call_logs[from_number]
        else:
            call_logs[from_number].append({"role": "assistant", "content": ai_response})
            xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="Polly.Joanna-Neural">
                    <prosody rate="98%">{ai_response}</prosody>
                </Say>
                <Gather input="speech" action="/handle-response" speechTimeout="4" />
            </Response>"""
            
    except Exception as e:
        print(f"Error: {e}")
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">We are experiencing technical difficulties. Please try your call again shortly.</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="4" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

@app.route("/hq-chat", methods=['POST'])
def hq_chat():
    """Acts as a secure API bridge proxy for the global Management Dashboard."""
    try:
        data = request.json
        system_instructions = data.get("system", "")
        conversation_history = data.get("messages", [])
        
        payload = [{"role": "system", "content": system_instructions}] + conversation_history
        
        completion = groq_client.chat.completions.create(
            messages=payload, 
            model="llama-3.1-8b-instant"
        )
        
        ai_reply = completion.choices[0].message.content
        return {"reply": ai_reply}
        
    except Exception as e:
        print(f"HQ Dashboard Bridge error: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
