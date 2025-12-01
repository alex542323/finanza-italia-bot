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
TG_MESSAGE_MAX = 800  # lunghezza massima desiderata per ogni singolo messaggio Telegram (utente ha chiesto messaggi brevi)

SECTION_TITLES = [
    "1) CATHIE WOOD & ARK INVEST",
    "2) BITCOIN & MERCATO CRYPTO",
    "3) MACROECONOMIA"
]

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
        
        # Prompt progettato per generare tre sezioni numerate (1,2,3).
        # È importante mantenere i numeri in testa alle sezioni perché il parser li userà.
        prompt = """Sei un esperto di investimenti e mercati crypto altamente qualificato.
Rispondi in tre sezioni numerate (1, 2, 3). Fornisci un BREVE resoconto per ogni sezione (1-2 frasi ciascuna), rispettando i seguenti punti:

1) CATHIE WOOD & ARK INVEST
   - Ultime strategie e dichiarazioni
   - Recenti movimenti nei crypto

2) BITCOIN & MERCATO CRYPTO
   - Prezzo e trend attuali
   - Principali movimenti oggi

3) MACROECONOMIA
   - Fed e liquidità
   - Impatto su crypto

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
            return None, meta

        print(f"[OK] Report generato: {len(report)} caratteri")
        return report, meta
        
    except Exception as e:
        print(f"[ERRORE] Gemini API: {type(e).__name__}: {str(e)}")
        return None, {"error": str(e)}

def split_report_into_sections(report):
    """
    Prova a estrarre tre sezioni numerate dal testo (1., 2., 3.).
    Se non riesce, ritorna tre porzioni approssimate di lunghezza uguale.
    """
    if not report:
        return []

    # Primo tentativo: trovare posizioni di '1.', '2.' e '3.' all'inizio di una linea
    positions = {}
    for i in (1, 2, 3):
        m = re.search(r'(?m)^\s*' + str(i) + r'[\).\s-]+', report)
        if m:
            positions[i] = m.start()

    sections = []
    if 1 in positions and 2 in positions:
        # usa i boundaries trovati; se manca '3' prendi fino alla fine
        start1 = positions[1]
        start2 = positions[2]
        start3 = positions.get(3, None)
        sec1 = report[start1:start2].strip()
        if start3:
            sec2 = report[start2:start3].strip()
            sec3 = report[start3:].strip()
        else:
            sec2 = report[start2:].strip()
            sec3 = ""
        sections = [sec1, sec2, sec3]
        # rimuovi eventuali numerazioni iniziali "1." ecc
        sections = [re.sub(r'^\s*\d+[\).\s-]+\s*', '', s, count=1).strip() for s in sections if s is not None]
        # assicurati di avere esattamente 3 voci (padding vuote se necessario)
        while len(sections) < 3:
            sections.append("")
        return sections[:3]

    # Secondo tentativo: split by "###SECTION" markers (se l'utente ha usato un altro stile)
    if "###SECTION" in report:
        parts = re.split(r'###SECTION\d+###', report)
        parts = [p.strip() for p in parts if p.strip()]
        # normalizza a 3
        while len(parts) < 3:
            parts.append("")
        return parts[:3]

    # Fallback: suddividi in 3 parti per parole
    words = report.split()
    if not words:
        return ["", "", ""]
    total = len(words)
    part = math.ceil(total / 3)
    s1 = " ".join(words[0:part]).strip()
    s2 = " ".join(words[part:part*2]).strip()
    s3 = " ".join(words[part*2:]).strip()
    return [s1, s2, s3]

def build_three_telegram_messages(report, meta):
    """
    Costruisce tre messaggi Telegram, uno per ciascuna sezione.
    Se report è None, costruisce tre messaggi fallback molto brevi (o un solo messaggio di errore).
    """
    timestamp = datetime.now().strftime('%d/%m/%Y ore %H:%M CET')

    if not report:
        # Messaggio di fallback breve (in un unico messaggio)
        reason = meta.get("finish_reason") or meta.get("error") or "Nessuna risposta valida"
        msg = f"⚠️ Nessun contenuto generato da Gemini.\nMotivo: {reason}"
        if meta.get("safety_info"):
            msg += "\nSafety: risposta bloccata"
        header_footer = f"🚀 CATHIE WOOD & CRYPTO MARKET REPORT\n⏰ {timestamp}\n\n"
        footer = "\n\n---\n✅ Powered by Google Gemini AI 2.5\n📲 Bot Telegram Automazione Finanza"
        # Inviaamo il fallback come singolo messaggio
        return [header_footer + msg + footer]

    # Ottieni le 3 sezioni
    secs = split_report_into_sections(report)

    messages = []
    for idx, sec in enumerate(secs):
        title = SECTION_TITLES[idx] if idx < len(SECTION_TITLES) else f"{idx+1}) Sezione"
        header = f"🚀 {title}\n⏰ {timestamp}\n\n"
        # Troncamento per sicurezza
        text = sec.strip()
        if not text:
            text = "(Nessun contenuto per questa sezione)"
        if len(text) > TG_MESSAGE_MAX:
            text = text[:TG_MESSAGE_MAX].rstrip() + "\n\n... (troncato)"
        footer = "\n\n---\n✅ Powered by Google Gemini AI 2.5" if idx == len(secs)-1 else ""  # footer solo sull'ultimo messaggio
        # aggiungiamo un indicatore 1/3, 2/3, 3/3
        pagesuffix = f"\n\n({idx+1}/3)"
        messages.append(header + text + pagesuffix + footer)
    return messages

def invia_telegram_con_retry(testo, retry=0):
    """Invia messaggio a Telegram con retry e gestione errori"""
    
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[ERRORE] Credenziali Telegram mancanti!")
        return False
    
    if not testo or len(testo) == 0:
        print("[ERRORE] Messaggio vuoto!")
        return False
    
    # Dividi messaggi lunghi (ma build_three_telegram_messages dovrebbe già produrre messaggi brevi)
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
    
    # Costruisci fino a tre messaggi per Telegram
    messages = build_three_telegram_messages(report, meta)
    
    # Step 4: Invia su Telegram — invia ogni messaggio separatamente
    print("\n[STEP 2] Invio a Telegram dei singoli messaggi (3)...")
    all_ok = True
    for idx, m in enumerate(messages, start=1):
        print(f"[INFO] Invio messaggio {idx}/{len(messages)}...")
        ok = invia_telegram_con_retry(m)
        if not ok:
            all_ok = False
            print(f"[ERRORE] Invio messaggio {idx} fallito.")
        # piccolo delay per evitare ratelimit
        time.sleep(1)
    
    # Step 5: Resoconto finale
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
