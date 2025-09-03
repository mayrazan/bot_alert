import requests
import json
import os
from collections import defaultdict
from datetime import datetime

# --- CONFIGURAÇÃO ---
NYCC_API_URL = "https://conventions.leapevent.tech/api/schedules?key=7b399b7c-63e3-4c10-83b5-6e53559dc289"
LAST_FILE = "last_updates_nycc.json"

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DISCORD
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- FUNÇÕES ---
def get_data(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def load_last_state():
    if os.path.exists(LAST_FILE):
        try:
            with open(LAST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_state(state):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def parse_day(dt_str):
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").date()
    except:
        return None

def organize_schedules(schedules):
    organized = defaultdict(lambda: defaultdict(list))
    for s in schedules:
        start_time = s.get("start_time")
        day = parse_day(start_time) if start_time else None
        location = s.get("location") or (s.get("venue_location") or {}).get("name", "Unknown")
        if not day:
            continue
        organized[str(day)][location].append(s)
    return dict(organized)

def format_message(organized):
    msg_lines = []
    for day, locations in sorted(organized.items()):
        msg_lines.append(f"*{day}*")
        for location, panels in locations.items():
            msg_lines.append(f"🏢 _{location}_\n────────────────────────────")
            for s in panels:
                title = s.get("title", "(sem título)")
                start_raw = s.get("start_time")
                end_raw = s.get("end_time")
                start = start_raw[11:16] if isinstance(start_raw, str) and len(start_raw) >= 16 else "??:??"
                end = end_raw[11:16] if isinstance(end_raw, str) and len(end_raw) >= 16 else "??:??"
                desc = s.get("description", "")
                def guest_name(p):
                    fn = p.get("first_name", "")
                    ln = p.get("last_name", "")
                    alt = p.get("alt_name", "")
                    base = (fn + " " + ln).strip()
                    if alt:
                        return f"{base} ({alt})"
                    return base
                guests_list = [guest_name(p) for p in s.get("people", [])]
                guests = s.get("people_list") or ", ".join(guests_list)
                # NOVO/ATUALIZADO
                tag = ""
                if s.get("_new"):
                    tag = " (NOVO)"
                elif s.get("_updated_fields"):
                    tag = " (ATUALIZADO)"
                # Título em negrito
                msg_lines.append(f"🕒 {start}-{end} | **{title}**{tag}")
                # Guests
                if guests_list:
                    if len(guests_list) > 3:
                        msg_lines.append("👤 Guests:")
                        for g in guests_list:
                            msg_lines.append(f"   • {g}")
                    else:
                        msg_lines.append(f"👤 Guests: {guests}")
                elif guests:
                    msg_lines.append(f"👤 Guests: {guests}")
                # Descrição (limitada a 120 chars)
                if desc:
                    short_desc = desc.replace("\n", " ").strip()
                    msg_lines.append(f"📝 {short_desc[:120]}{'...' if len(short_desc)>120 else ''}")
                msg_lines.append("")
            msg_lines.append("────────────────────────────")
    return "\n".join(msg_lines)

def send_telegram(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        
        # Limita mensagem a 4000 caracteres (limite do Telegram é 4096)
        if len(message) > 4000:
            message = message[:3950] + "...\n\n(Mensagem truncada)"
        
        try:
            response = requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID, 
                "text": message, 
                "parse_mode": "Markdown"
            }, timeout=30)
            response.raise_for_status()
            print(f"[TELEGRAM] Mensagem enviada com sucesso")
        except Exception as e:
            print(f"[TELEGRAM ERROR] Falha ao enviar: {e}")
            # Tenta enviar sem markdown como fallback
            try:
                response = requests.post(url, data={
                    "chat_id": TELEGRAM_CHAT_ID, 
                    "text": message
                }, timeout=30)
                response.raise_for_status()
                print(f"[TELEGRAM] Mensagem enviada sem formatação")
            except Exception as e2:
                print(f"[TELEGRAM ERROR] Falha total: {e2}")
    else:
        print("[MOCK TELEGRAM] Mensagem:")
        print(message)

def send_discord(message):
    if DISCORD_WEBHOOK_URL:
        # Limita mensagem a 2000 caracteres (limite do Discord)
        if len(message) > 2000:
            message = message[:1950] + "...\n\n(Mensagem truncada)"
        
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=30)
            response.raise_for_status()
            print(f"[DISCORD] Mensagem enviada com sucesso")
        except Exception as e:
            print(f"[DISCORD ERROR] Falha ao enviar: {e}")
    else:
        print("[MOCK DISCORD] Mensagem:")
        print(message)

def build_panel_state(panel):
    # Estado relevante para detectar mudanças
    def guest_name(p):
        fn = p.get("first_name", "")
        ln = p.get("last_name", "")
        alt = p.get("alt_name", "")
        base = (fn + " " + ln).strip()
        if alt:
            return f"{base} ({alt})"
        return base
    return {
        "title": panel.get("title", ""),
        "description": panel.get("description", ""),
        "people_list": panel.get("people_list", ""),
        "people": [guest_name(p) for p in panel.get("people", [])],
    }

def main():
    data = get_data(NYCC_API_URL)
    schedules = data.get("schedules", [])
    last_state = load_last_state()
    new_state = {}
    new_panels = []

    for s in schedules:
        pid = str(s.get("id"))
        state = build_panel_state(s)
        new_state[pid] = state
        old = last_state.get(pid)
        if not old or old != state:
            # Novo painel ou painel alterado
            panel_copy = s.copy()
            # Marcar novidades
            if not old:
                panel_copy["_new"] = True
            else:
                changes = []
                for k in state:
                    if old.get(k) != state[k]:
                        changes.append(k)
                panel_copy["_updated_fields"] = changes
            new_panels.append(panel_copy)

    if new_panels:
        organized = organize_schedules(new_panels)
        message = format_message(organized)
        send_telegram(message)
        send_discord(message)
        print("Notificação enviada.")
    else:
        print("Sem novidades.")
    save_last_state(new_state)

if __name__ == "__main__":
    main()
