import os
import requests
from datetime import datetime
import google.generativeai as genai

# --- CARICA VARIABILI D'AMBIENTE ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def ottieni_report_cathie_wood_crypto():
    """Genera report su Cathie Wood, ARK Invest e Crypto Market"""
    
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY non configurata nei Secrets di GitHub"
    
    try:
        print("[INFO] Connessione a Google Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = """Sei un esperto di investimenti e mercati crypto. 
Fornisci un dettagliato resoconto (max 300 parole) su:

1. **CATHIE WOOD & ARK INVEST**
   - Ultime dichiarazioni e previsioni di Cathie Wood
   - Recenti acquisizioni di ARK Invest nel settore crypto e tech
   - Strategie di investimento di ARK Invest

2. **BITCOIN & MERCATO CRYPTO**
   - Prezzo attuale e movimenti recenti di Bitcoin
   - Performance di Ethereum e altre crypto principali
   - Trend del mercato crypto oggi

3. **FATTORI MACROECONOMICI**
   - Politiche della Fed rilevanti
   - Situazione di liquidità nei mercati
   - Impatto su crypto e azioni tech

Formato: Usa emoji, punti elenco e sezioni chiare. Sii specifico con i numeri e le percentuali."""
        
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
    print("=" * 80)
    print(f"🤖 CATHIE WOOD & CRYPTO TRACKER - GEMINI + TELEGRAM")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)
    
    # Step 1: Genera report
    print("\n[STEP 1] Generazione report (Cathie Wood + Crypto Market)...")
    report = ottieni_report_cathie_wood_crypto()
    
    # Step 2: Prepara messaggio formattato
    messaggio = f"""🚀 *CATHIE WOOD & CRYPTO MARKET DAILY REPORT*
⏰ Generato: {datetime.now().strftime('%d/%m/%Y ore %H:%M')}

{report}

---
*Powered by Google Gemini AI + Telegram Bot*
*Aggiornamenti quotidiani: 08:00 CET* ✅"""
    
    # Step 3: Invia su Telegram
    print("\n[STEP 2] Invio a Telegram...")
    success = invia_telegram(messaggio)
    
    # Step 4: Resoconto finale
    print("\n" + "=" * 80)
    if success:
        print("✅ AUTOMAZIONE COMPLETATA CON SUCCESSO")
    else:
        print("⚠️  AUTOMAZIONE COMPLETATA CON ERRORI")
    print("=" * 80)

if __name__ == "__main__":
    main()
