import os
import requests
from datetime import datetime
import google.generativeai as genai
import time
import pprint

# --- CARICA VARIABILI D'AMBIENTE ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Configurazione
MAX_RETRIES = 3
RETRY_DELAY = 2
TG_MAX_LENGTH = 4096

def _extract_text_and_safety_from_response(response):
    """
    Tenta di estrarre il testo dalla response di Gemini in modo robusto
    e restituisce una tupla (text, safety_info) dove text può essere None
    se la risposta è stata bloccata o non contiene testo.
    Questo gestisce diversi formati di oggetto di risposta.
    """
    safety_info = []
    text = None

    # 1) Quick accessor (se disponibile)
    try:
        if hasattr(response, "text") and response.text:
            text = response.text.strip()
            return text, safety_info
    except Exception:
        # fallthrough, user saw an error con questo accessor
        pass

    # 2) Cerca "candidates" o altri attributi comuni
    candidates = None
    for attr in ("candidates", "outputs", "responses", "items"):
        if hasattr(response, attr):
            try:
                candidates = getattr(response, attr)
                break
            except Exception:
                candidates = None

    if candidates:
        try:
            for idx, c in enumerate(candidates):
                # Raccogli info di safety se presenti
                for sattr in ("safety_ratings", "safetyRatings", "safety"):
                    if hasattr(c, sattr):
                        try:
                            safety_info.append({sattr: getattr(c, sattr)})
                        except Exception:
                            safety_info.append({sattr: repr(getattr(c, sattr))})

                # Proviamo diversi nomi possibili per il testo
                for tattr in ("content", "text", "output", "message", "candidate"):
                    if hasattr(c, tattr):
                        try:
                            val = getattr(c, tattr)
                            # se è stringa
                            if isinstance(val, str) and val.strip():
                                return val.strip(), safety_info
                            # se è un oggetto con sub-attributi
                            for sub in ("text", "content"):
                                if hasattr(val, sub):
                                    subval = getattr(val, sub)
                                    if isinstance(subval, str) and subval.strip():
                                        return subval.strip(), safety_info
                        except Exception:
                            continue

                # fallback: prova a convertire l'oggetto candidato in stringa
                try:
                    s = str(c).strip()
                    if s:
                        return s, safety_info
                except Exception:
                    continue
        except Exception:
            pass

    # 3) Ultimo tentativo: stampa repr() dell'intera response (per debug)
    try:
        repr_resp = repr(response)
        if repr_resp and len(repr_resp) < 5000:
            return repr_resp, safety_info
    except Exception:
        pass

    return None, safety_info

def ottieni_report_cathie_wood_crypto():
    """Genera report su Cathie Wood, ARK Invest e Crypto Market - VERSIONE STABILE"""
    
    if not GEMINI_API_KEY:
        print("[ERRORE] GEMINI_API_KEY non configurata!")
        return None
    
    try:
        print("[INFO] Configurazione Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Usa il modello CORRETTO: gemini-2.5-flash
        print("[INFO] Usando modello: gemini-2.5-flash (STABILE)")
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """Sei un esperto di investimenti e mercati crypto altamente qualificato.

Fornisci un BREVE resoconto (150-200 parole) su:

1. **CATHIE WOOD & ARK INVEST**
   - Ultime strategie e dichiarazioni
   - Recenti movimenti nei crypto

2. **BITCOIN & MERCATO CRYPTO**
   - Prezzo e trend attuali
   - Principali movimenti oggi

3. **MACROECONOMIA**
   - Fed e liquidità
   - Impatto su crypto

Sii conciso e specifico con numeri."""
        
        print("[INFO] Invio richiesta a Gemini...")
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=800,
                temperature=0.7,
            )
        )

        # Estrai testo in modo robusto e raccogli eventuali informazioni di safety
        report, safety_info = _extract_text_and_safety_from_response(response)

        # Se non abbiamo testo, controlliamo safety_info per capire se è stato bloccato
        if not report:
            print("[ERRORE] Nessun testo estratto dalla risposta di Gemini.")
            if safety_info:
                print("[INFO] Safety info trovata:")
                pprint.pprint(safety_info)
                # Prova a verificare se qualche rating indica blocco esplicito
                blocked = False
                try:
                    for s in safety_info:
                        # safety_info è una lista di dict: controlliamo ricorsivamente
                        def find_block(x):
                            if isinstance(x, dict):
                                for k, v in x.items():
                                    if isinstance(v, dict) and v.get("blocked") is True:
                                        return True
                                    if isinstance(v, (list, dict)):
                                        if find_block(v):
                                            return True
                            if isinstance(x, list):
                                for e in x:
                                    if find_block(e):
                                        return True
                            return False
                        if find_block(s):
                            blocked = True
                            break
                except Exception:
                    blocked = False

                if blocked:
                    print("[ERRORE] La risposta sembra essere stata bloccata per motivi di safety. Rivedi e attenua il prompt.")
                else:
                    print("[ERRORE] La risposta non contiene una parte testuale utilizzabile. Stampa completa della response per debug:")
                    try:
                        pprint.pprint(response)
                    except Exception:
                        print(repr(response))
            else:
                print("[ERRORE] Nessuna informazione di safety disponibile. Stampa completa della response per debug:")
                try:
                    pprint.pprint(response)
                except Exception:
                    print(repr(response))
            return None
        
        print(f"[OK] Report generato: {len(report)} caratteri")
        return report
        
    except Exception as e:
        print(f"[ERRORE] Gemini API: {type(e).__name__}: {str(e)}")
        return None

def invia_telegram_con_retry(testo, retry=0):
    """Invia messaggio a Telegram con retry e gestione errori"""
    
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[ERRORE] Credenziali Telegram mancanti!")
        return False
    
    if not testo or len(testo) == 0:
        print("[ERRORE] Messaggio vuoto!")
        return False
    
    # Dividi messaggi lunghi
    chunks = [testo[i:i+TG_MAX_LENGTH] for i in range(0, len(testo), TG_MAX_LENGTH)]
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    
    all_sent = True
    for idx, chunk in enumerate(chunks, 1):
        payload = {
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown"
        }
        
        try:
            print(f"[INFO] Invio messaggio {idx}/{len(chunks)} ({len(chunk)} char)...")
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                print(f"[OK] Messaggio {idx} inviato con successo")
            else:
                print(f"[AVVERTENZA] Status {response.status_code}: {response.text}")
                if retry < MAX_RETRIES:
                    print(f"[INFO] Retry in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    return invia_telegram_con_retry(chunk, retry + 1)
                all_sent = False
                
        except requests.exceptions.Timeout:
            print("[ERRORE] Timeout invio Telegram")
            if retry < MAX_RETRIES:
                print(f"[INFO] Retry in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                return invia_telegram_con_retry(chunk, retry + 1)
            all_sent = False
        except Exception as e:
            print(f"[ERRORE] Eccezione Telegram: {type(e).__name__}: {str(e)}")
            if retry < MAX_RETRIES:
                print(f"[INFO] Retry in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                return invia_telegram_con_retry(chunk, retry + 1)
            all_sent = False
        
        # Pausa tra i messaggi
        if idx < len(chunks):
            time.sleep(1)
    
    return all_sent

def main():
    print("=" * 80)
    print(f"🚀 CATHIE WOOD & CRYPTO TRACKER - PRODUCTION READY")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S CET')}")
    print("=" * 80)
    
    # Step 1: Verifica credenziali
    print("\n[VERIFICA] Credenziali configurate:")
    print(f"  - GEMINI_API_KEY: {'✅' if GEMINI_API_KEY else '❌'}")
    print(f"  - TELEGRAM_TOKEN: {'✅' if TG_TOKEN else '❌'}")
    print(f"  - TELEGRAM_CHAT_ID: {'✅' if TG_CHAT_ID else '❌'}")
    
    if not all([GEMINI_API_KEY, TG_TOKEN, TG_CHAT_ID]):
        print("\n[ERRORE CRITICO] Mancano credenziali! Aborto.")
        return False
    
    # Step 2: Genera report
    print("\n[STEP 1] Generazione report Cathie Wood + Crypto...")
    report = ottieni_report_cathie_wood_crypto()
    
    if not report:
        print("[ERRORE] Impossibile generare report da Gemini")
        return False
    
    # Step 3: Prepara messaggio finale
    messaggio = f"""🚀 **CATHIE WOOD & CRYPTO MARKET REPORT**
⏰ {datetime.now().strftime('%d/%m/%Y ore %H:%M CET')}

{report}

---
✅ *Powered by Google Gemini AI 2.5*
📲 *Bot Telegram Automazione Finanza*
⏰ *Aggiornamento giornaliero: 08:00 CET*"""
    
    # Step 4: Invia su Telegram
    print("\n[STEP 2] Invio a Telegram...")
    success = invia_telegram_con_retry(messaggio)
    
    # Step 5: Resoconto finale
    print("\n" + "=" * 80)
    if success:
        print("✅✅✅ AUTOMAZIONE COMPLETATA CON SUCCESSO ✅✅✅")
        print("Messaggio inviato a Telegram!")
    else:
        print("❌ ERRORE: Impossibile inviare il messaggio a Telegram")
    print("=" * 80)
    
    return success

if __name__ == "__main__":
    main()
