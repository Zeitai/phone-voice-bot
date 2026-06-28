import os
from flask import Flask, request, Response
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)
CORS(app)

# --- SECURE API KEY CONFIGURATION ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# --- PURE HINDI CUSTOM RECEPTONIST PROMPT ---
SYSTEM_PROMPT = (
    "आप सिटी हॉस्पिटल (City Hospital) की एक बहुत ही विनम्र, मददगार और पेशेवर महिला एआई रिसेप्शनिस्ट (AI Receptionist) हैं। "
    "आपको केवल और केवल शुद्ध हिंदी (Hindi script) या प्राकृतिक बातचीत वाली हिंदी में ही बात करनी है। अंग्रेजी का उपयोग पूरी तरह से बंद कर दें। "
    "मरीज से बहुत प्यार और सम्मान से बात करें (जैसे 'जी बताएं', 'मैं आपकी क्या सेवा कर सकती हूँ?')। "
    "मरीज से उनका नाम, बीमारी या डॉक्टर का विभाग, और अपॉइंटमेंट का समय आराम से एक-एक करके पूछें। "
    "याद रखें: जवाब बहुत छोटा, प्यारा और सीधा होना चाहिए (सिर्फ 1 से 2 वाक्य)। कोई फालतू की अंग्रेजी या मुश्किल शब्द न बोलें।"
)

# Active session tracking dictionary
call_logs = {}

@app.route("/incoming-call", methods=['POST'])
def incoming_call():
    """Triggered instantly when a patient dials the hospital line."""
    from_number = request.form.get("From", "unknown")
    
    # Initialize session history with the pure Hindi prompt
    call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Pure Hindi warm greeting
    greeting = "सिटी हॉस्पिटल में आपका स्वागत है। मैं आपकी क्या सहायता कर सकती हूँ?"
    call_logs[from_number].append({"role": "assistant", "content": greeting})
    
    # Using 'alice' with 'hi-IN' right from the start for native accent
    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say voice="alice" language="hi-IN">{greeting}</Say>
        <Gather input="speech" action="/handle-response" speechTimeout="auto" />
    </Response>"""
    return Response(xml_data, mimetype='text/xml')

@app.route("/handle-response", methods=['POST'])
def handle_response():
    """Processes incoming transcribed text inputs cleanly without static stream interruptions."""
    from_number = request.form.get("From", "unknown")
    user_speech = request.form.get("SpeechResult", "")
    
    if not user_speech:
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice" language="hi-IN">माफ़ कीजिएगा, मैं आपकी आवाज़ सुन नहीं पाई। क्या आप दोबारा बोलेंगे?</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
        return Response(xml_data, mimetype='text/xml')
        
    if from_number not in call_logs:
        call_logs[from_number] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    print(f"🗣️ User Said: {user_speech}")
    call_logs[from_number].append({"role": "user", "content": user_speech})
    
    try:
        completion = groq_client.chat.completions.create(
            messages=call_logs[from_number], model="llama-3.3-70b-versatile"
        )
        ai_response = completion.choices[0].message.content
        print(f"🤖 AI Response: {ai_response}")
        call_logs[from_number].append({"role": "assistant", "content": ai_response})
        
        # Enforcing free native Hindi engine for all responses
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice" language="hi-IN">{ai_response}</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
    except Exception as e:
        print(f"Error: {e}")
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice" language="hi-IN">क्षमा करें, सर्वर में कुछ दिक्कत आ रही है। कृपया थोड़ी देर बाद प्रयास करें।</Say>
            <Gather input="speech" action="/handle-response" speechTimeout="auto" />
        </Response>"""
        
    return Response(xml_data, mimetype='text/xml')

@app.route("/hq-chat", methods=['POST'])
def hq_chat():
    """Acts as a secure API bridge proxy for the Zeit AI HQ Dashboard."""
    try:
        data = request.json
        system_instructions = data.get("system", "")
        conversation_history = data.get("messages", [])
        
        payload = [{"role": "system", "content": system_instructions}] + conversation_history
        
        completion = groq_client.chat.completions.create(
            messages=payload, 
            model="llama-3.3-70b-versatile"
        )
        
        ai_reply = completion.choices[0].message.content
        return {"reply": ai_reply}
        
    except Exception as e:
        print(f"HQ Dashboard Bridge error: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
