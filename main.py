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
TG_MESSAGE_MAX = 800  # lunghezza massima desiderata per il messaggio Telegram (più breve)

def _extract_text_and_safety_from_response(response):
    """
    Estrae testo e info di safety da diversi formati di response del client Gemini.
    Ritorna (text, meta) dove meta è un dict con finish_reason e safety_info utili al fallback.
    """
    safety_info = []
    meta = {}
    text = None

    # Finish reason / metadata per debug
    for fname in ("finishreason", "finish_reason", "finishReason"):
        if hasattr(response, fname):
            try:
                meta["finish_reason"] = getattr(response, fname)
            except Exception:
                meta["finish_reason"] = repr(getattr(response, fname))

    # Quick accessor (se disponibile)
    try:
        if hasattr(response, "text") and response.text:
            text = response.text.strip()
            return text, meta
    except Exception:
        pass

    # Cerca candidati / outputs
    candidate_containers = []
    for attr in ("candidates", "outputs", "responses", "items", "output"):
        if hasattr(response, attr):
            try:
                val = getattr(response, attr)
                candidate_containers.append(val)
            except Exception:
                continue

    candidates = []
    for cset in candidate_containers:
        try:
            if isinstance(cset, (list, tuple)):
                candidates.extend(cset)
            else:
                candidates.append(cset)
        except Exception:
            continue

    # Funzione ricorsiva per estrarre testo da strutture annidate
    def extract_text_from_obj(obj):
        if isinstance(obj, str) and obj.strip():
            return obj.strip()
        if isinstance(obj, dict):
            for key in ("content", "text", "output", "message", "body"):
                if key in obj and obj[key]:
                    res = extract_text_from_obj(obj[key])
                    if res:
                        return res
            for v in obj.values():
                res = extract_text_from_obj(v)
                if res:
                    return res
        if isinstance(obj, (list, tuple)):
            for el in obj:
                res = extract_text_from_obj(el)
                if res:
                    return res
        try:
            for attr in ("content", "text", "output", "message"):
                if hasattr(obj, attr):
                    val = getattr(obj, attr)
                    res = extract_text_from_obj(val)
                    if res:
                        return res
        except Exception:
            pass
        return None

    sample_types = []
    for c in candidates:
        sample_types.append(type(c).__name__)
        for sattr in ("safety_ratings", "safetyRatings", "safety"):
            if hasattr(c, sattr):
                try:
                    safety_info.append({sattr: getattr(c, sattr)})
                except Exception:
                    safety_info.append({sattr: repr(getattr(c, sattr))})
        try:
            t = extract_text_from_obj(c)
            if t:
                meta["sample_candidates"] = sample_types
                if safety_info:
                    meta["safety_info"] = safety_info
                return t, meta
        except Exception:
            continue

    # Ultimo tentativo: prova response.output
    try:
        if hasattr(response, "output"):
            out = getattr(response, "output")
            t = extract_text_from_obj(out)
            if t:
                meta["sample_output_type"] = type(out).__name__
                if safety_info:
                    meta["safety_info"] = safety_info
                return t, meta
    except Exception:
        pass

    if safety_info:
        meta["safety_info"] = safety_info
    meta.setdefault("sample_candidates", sample_types)
    return None, meta

def ottieni_report_cathie_wood_crypto():
    """Genera report su Cathie Wood, ARK Invest e Crypto Market - VERSIONE STABILE"""
    
    if not GEMINI_API_KEY:
        print("[ERRORE] GEMINI_API_KEY non configurata!")
        return None, {}

    try:
        print("[INFO] Configurazione Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
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
                max_output_tokens=1500,
                temperature=0.7,
            )
        )

        # debug della finish reason se presente
        for attr in ("finishreason", "finish_reason", "finishReason"):
            if hasattr(response, attr):
                try:
                    print(f"[DEBUG] {attr}: {getattr(response, attr)}")
                except Exception:
                    pass

        report, meta = _extract_text_and_safety_from_response(response)
        if not report:
            print("[ERRORE] Nessun testo estratto dalla risposta di Gemini.")
            if meta.get("safety_info"):
                print("[INFO] Safety info trovata:")
                pprint.pprint(meta["safety_info"])
            print("[INFO] Meta:", {k: meta.get(k) for k in ("finish_reason","sample_candidates","sample_output_type") if k in meta})
            # Ritorniamo meta per poter costruire un messaggio di fallback compatto
            return None, meta

        print(f"[OK] Report generato: {len(report)} caratteri")
        return report, meta
        
    except Exception as e:
        print(f"[ERRORE] Gemini API: {type(e).__name__}: {str(e)}")
        return None, {"error": str(e)}

def build_telegram_message(report, meta):
    """Costruisce un messaggio Telegram breve e sicuro per la lunghezza."""
    header = f"🚀 CATHIE WOOD & CRYPTO MARKET REPORT\n⏰ {datetime.now().strftime('%d/%m/%Y ore %H:%M CET')}\n\n"
    footer = "\n\n---\n✅ Powered by Google Gemini AI 2.5\n📲 Bot Telegram Automazione Finanza"
    
    if not report:
        # Messaggio di fallback molto breve
        reason = meta.get("finish_reason") or meta.get("error") or "Nessuna risposta valida"
        msg = f"⚠️ Nessun contenuto generato da Gemini.\nMotivo: {reason}"
        # aggiungi info safety se presente (compatta)
        if meta.get("safety_info"):
            msg += "\nSafety: risposta bloccata"
        return header + msg + footer

    # Troncamento sicuro per Telegram (richiesta dell'utente: messaggi corti)
    if len(report) > TG_MESSAGE_MAX:
        short = report[:TG_MESSAGE_MAX].rstrip()
        short += "\n\n... (troncato)"
    else:
        short = report

    # Manteniamo il messaggio in Markdown semplice
    return header + short + footer

def invia_telegram_con_retry(testo, retry=0):
    """Invia messaggio a Telegram con retry e gestione errori"""
    
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[ERRORE] Credenziali Telegram mancanti!")
        return False
    
    if not testo or len(testo) == 0:
        print("[ERRORE] Messaggio vuoto!")
        return False
    
    # Dividi messaggi lunghi (ma costruiamo messaggi già brevi con build_telegram_message)
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
    report, meta = ottieni_report_cathie_wood_crypto()
    
    # Costruisci messaggio breve per Telegram (anche in caso di fallback)
    messaggio = build_telegram_message(report, meta)
    
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
