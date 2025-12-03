import os
import requests
from datetime import datetime
import google.generativeai as genai
import time
import pprint
import re
import math

# --- CARICA VARIABILI D'AMBIENTE ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Configurazione
MAX_RETRIES = 3
RETRY_DELAY = 2
TG_MAX_LENGTH = 4096
TG_CHUNK_SIZE = 4000  # l'utente ha richiesto 2000 caratteri per i primi due messaggi

SECTION_TITLES = [
    "1) Indtroduzione",
    "2) body",
    "3) Fine"
]

def _extract_text_and_safety_from_response(response):
    safety_info = []
    meta = {}
    text = None

    for fname in ("finishreason", "finish_reason", "finishReason"):
        if hasattr(response, fname):
            try:
                meta["finish_reason"] = getattr(response, fname)
            except Exception:
                meta["finish_reason"] = repr(getattr(response, fname))

    try:
        if hasattr(response, "text") and response.text:
            text = response.text.strip()
            return text, meta
    except Exception:
        pass

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
    if not GEMINI_API_KEY:
        print("[ERRORE] GEMINI_API_KEY non configurata!")
        return None, {}

    try:
        print("[INFO] Configurazione Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        print("[INFO] Usando modello: gemini-2.5-flash (STABILE)")
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """Sei un esperto di investimenti e mercati finaziari altamente qualificato.
Rispondi in tre sezioni numerate (1, 2, 3). Fornisci un BREVE resoconto per ogni sezione (1-2 frasi ciascuna), rispettando i seguenti punti:

1) Primo
   - What should I know before the markets open today

2) ETF
   - Prezzo etf e trend attuali
   - Principali movimenti oggi
3) 

IMPORTANTE: Inizia ogni sezione con "1.", "2." e "3." (ad es. "1. ..."), ogni sezione deve essere breve (1-2 frasi). Non includere altri numeri fuori dalle intestazioni delle tre sezioni.
"""

        print("[INFO] Invio richiesta a Gemini...")
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=800,
                temperature=0.7,
            )
        )

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
            return None, meta

        print(f"[OK] Report generato: {len(report)} caratteri")
        return report, meta
        
    except Exception as e:
        print(f"[ERRORE] Gemini API: {type(e).__name__}: {str(e)}")
        return None, {"error": str(e)}

def build_three_telegram_messages(report, meta):
    """
    Spezza il testo in esattamente 3 messaggi:
    - primo: primi TG_CHUNK_SIZE caratteri (2000)
    - secondo: successivi TG_CHUNK_SIZE caratteri (2000)
    - terzo: il resto (qualsiasi lunghezza)
    Se report è None invia un fallback compatto (1 messaggio).
    """
    timestamp = datetime.now().strftime('%d/%m/%Y ore %H:%M CET')
    header_base = f"🚀 CATHIE WOOD & CRYPTO MARKET REPORT\n⏰ {timestamp}\n\n"
    footer = "\n\n---\n✅ Powered by Google Gemini AI 2.5\n📲 Bot Telegram Automazione Finanza"

    if not report:
        reason = meta.get("finish_reason") or meta.get("error") or "Nessuna risposta valida"
        msg = f"⚠️ Nessun contenuto generato da Gemini.\nMotivo: {reason}"
        if meta.get("safety_info"):
            msg += "\nSafety: risposta bloccata"
        return [header_base + msg + footer]

    # Creazione esatta dei tre chunk richiesti
    a = report[0:TG_CHUNK_SIZE].rstrip()
    b = report[TG_CHUNK_SIZE:TG_CHUNK_SIZE*2].rstrip()
    c = report[TG_CHUNK_SIZE*2:].rstrip()

    # Se uno dei chunk è vuoto, metti un placeholder minimo per mantenere 3 messaggi
    if not a:
        a = "(Nessun contenuto - parte 1 vuota)"
    if not b:
        b = "(Nessun contenuto - parte 2 vuota)"
    if not c:
        c = "(Nessun contenuto - parte 3 vuota)"

    messages = []
    parts = [a, b, c]
    for idx, part in enumerate(parts):
        title = SECTION_TITLES[idx] if idx < len(SECTION_TITLES) else f"Parte {idx+1}"
        header = f"🚀 {title}\n⏰ {timestamp}\n\n"
        text = part
        # Indica se è troncato localmente per chunk (solo sui primi due se la lunghezza è esattamente TG_CHUNK_SIZE e il report era più lungo)
        if idx < 2 and len(report) > (idx+1)*TG_CHUNK_SIZE and len(text) == TG_CHUNK_SIZE:
            text += "\n\n... (continua)"
        # Aggiungi footer solo sull'ultimo messaggio per non ripetere troppo
        msg_footer = footer if idx == 2 else ""
        pagesuffix = f"\n\n({idx+1}/3)"
        messages.append(header + text + pagesuffix + msg_footer)

    return messages

def invia_telegram_con_retry(testo, retry=0):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[ERRORE] Credenziali Telegram mancanti!")
        return False
    
    if not testo or len(testo) == 0:
        print("[ERRORE] Messaggio vuoto!")
        return False
    
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
            print(f"[INFO] Invio messaggio chunk {idx}/{len(chunks)} ({len(chunk)} char)...")
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                print(f"[OK] Messaggio chunk {idx} inviato con successo")
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
    
    print("\n[VERIFICA] Credenziali configurate:")
    print(f"  - GEMINI_API_KEY: {'✅' if GEMINI_API_KEY else '❌'}")
    print(f"  - TELEGRAM_TOKEN: {'✅' if TG_TOKEN else '❌'}")
    print(f"  - TELEGRAM_CHAT_ID: {'✅' if TG_CHAT_ID else '❌'}")
    
    if not all([GEMINI_API_KEY, TG_TOKEN, TG_CHAT_ID]):
        print("\n[ERRORE CRITICO] Mancano credenziali! Aborto.")
        return False
    
    print("\n[STEP 1] Generazione report Cathie Wood + Crypto...")
    report, meta = ottieni_report_cathie_wood_crypto()
    
    messages = build_three_telegram_messages(report, meta)
    
    print("\n[STEP 2] Invio a Telegram dei 3 messaggi (2000+2000+rest)...")
    all_ok = True
    for idx, m in enumerate(messages, start=1):
        print(f"[INFO] Invio messaggio {idx}/{len(messages)}...")
        ok = invia_telegram_con_retry(m)
        if not ok:
            all_ok = False
            print(f"[ERRORE] Invio messaggio {idx} fallito.")
        time.sleep(1)
    
    print("\n" + "=" * 80)
    if all_ok:
        print("✅✅✅ AUTOMAZIONE COMPLETATA CON SUCCESSO ✅✅✅")
        print("Messaggi inviati a Telegram!")
    else:
        print("❌ ERRORE: Uno o più messaggi non sono stati inviati correttamente")
    print("=" * 80)
    
    return all_ok

if __name__ == "__main__":
    main()
