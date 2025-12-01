import os
import requests
from datetime import datetime
import google.generativeai as genai

# --- CARICA VARIABILI D'AMBIENTE ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def ottieni_report_finanziario():
    """Genera report finanziario con Google Gemini API (GRATUITA)"""
    
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY non configurata nei Secrets di GitHub"
    
    try:
        print("[INFO] Connessione a Google Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = """Sei un esperto analista finanziario italiano. 
Fornisci un breve resoconto (max 200 parole) delle 3 notizie finanziarie più importanti di oggi:
- Mercati italiani ed europei
- Notizie economiche rilevanti
- Trend globali che impattano l'Italia

Formato: usa emoji e punti elenco per chiarezza."""
        
        print("[INFO] Generazione report con Gemini...")
        response = model.generate_content(prompt)
        
        report = response.text
        print(f"[OK] Report generato ({len(report)} caratteri)")
        return report
        
    except Exception as e:
        print(f"[ERRORE] Gemini API: {str(e)}")
        return f"❌ Errore nella generazione: {str(e)}"

def invia_telegram(testo):
    """Invia messaggio a Telegram"""
    
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[ERRORE] TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti!")
        return False
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown"
    }
    
    try:
        print("[INFO] Invio messaggio a Telegram...")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("[OK] Messaggio inviato su Telegram")
        return True
    except Exception as e:
        print(f"[ERRORE] Invio Telegram fallito: {str(e)}")
        return False

def main():
    print("=" * 70)
    print(f"🤖 AUTOMAZIONE FINANZA - GOOGLE GEMINI + TELEGRAM")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 70)
    
    # Step 1: Genera report con Gemini
    print("\n[STEP 1] Generazione report finanziario (Google Gemini)...")
    report = ottieni_report_finanziario()
    
    # Step 2: Prepara messaggio formattato
    messaggio = f"""📊 *REPORT FINANZIARIO GIORNALIERO*
⏰ Generato: {datetime.now().strftime('%d/%m/%Y ore %H:%M')}

{report}

---
*Powered by Google Gemini AI + Bot Telegram* ✅"""
    
    # Step 3: Invia su Telegram
    print("\n[STEP 2] Invio a Telegram...")
    success = invia_telegram(messaggio)
    
    # Step 4: Resoconto finale
    print("\n" + "=" * 70)
    if success:
        print("✅ AUTOMAZIONE COMPLETATA CON SUCCESSO")
    else:
        print("⚠️  AUTOMAZIONE COMPLETATA CON ERRORI")
    print("=" * 70)

if __name__ == "__main__":
    main()
