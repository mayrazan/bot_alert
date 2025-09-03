import requests
import json
import os
from collections import defaultdict
from datetime import datetime

# --- CONFIGURAÇÃO ---
EVENTS_URL = "https://prod-tickets.1iota.com/api/event/list"
CELEBS_URL = "https://prod-tickets.1iota.com/api/celeb/list"
LAST_FILE = "last_updates.json"

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DISCORD
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Intervalo de datas
START_FILTER = datetime(2025, 10, 5)
END_FILTER = datetime(2025, 10, 14)

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

def parse_day_str(day_str):
    try:
        return datetime.strptime(day_str.split(", ")[1] + " 2025", "%b %d %Y")
    except:
        return None

def organize_events(events):
    organized = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for e in events:
        if 125 not in e.get("projectLocationIds", []):
            continue

        day_str = e.get("localStartDay")
        day_dt = parse_day_str(day_str) if day_str else None
        if not day_dt or not (START_FILTER <= day_dt <= END_FILTER):
            continue

        show = e.get("title", "Show sem título")
        hour = e.get("when", "Horário não informado")

        guests_event = [g.get("name") for g in (e.get("guests") or [])]
        guests_project = [g.get("name") for g in (e.get("projectGuests") or [])]

        organized[day_dt][show][hour] = {
            "guests_event": guests_event,
            "guests_project": guests_project
        }

    return dict(sorted(organized.items()))

def format_message(organized_events):
    msg_lines = []
    for day, shows in sorted(organized_events.items()):
        msg_lines.append(f"*{day.strftime('%a, %b %d')}*")
        for show, times in shows.items():
            msg_lines.append(f"  {show}:")
            for hour, guests_dict in times.items():
                lines = []
                if guests_dict.get("guests_event"):
                    lines.append("🎤 Evento: " + ", ".join(guests_dict["guests_event"]))
                if guests_dict.get("guests_project"):
                    lines.append("⭐ Projeto: " + ", ".join(guests_dict["guests_project"]))
                
                guest_str = " | ".join(lines) if lines else "Nenhum guest listado"
                msg_lines.append(f"    {hour} → {guest_str}")
        msg_lines.append("")  # linha em branco entre dias
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

# --- EXECUÇÃO ---
def main():
    events = get_data(EVENTS_URL)
    celebs = get_data(CELEBS_URL)
    celeb_map = {c["id"]: c for c in celebs if c.get("isActive")}

    last_state = load_last_state()
    new_state = {}
    new_events = []

    def normalize_hour(hour):
        if not hour:
            return "unknown"
        h = hour.replace('Z', '')
        try:
            dt = datetime.fromisoformat(h)
            return dt.strftime('%Y-%m-%dT%H:%M:%S')
        except Exception:
            return h

    for e in events:
        day_str = e.get("localStartDay")
        day_dt = parse_day_str(day_str) if day_str else None
        if not day_dt or not (START_FILTER <= day_dt <= END_FILTER):
            continue

        eid = str(e["eventId"])
        hour_raw = e.get("startDateUtc") or e.get("when") or "unknown"
        hour = normalize_hour(hour_raw)
        key = f"{eid}_{hour}"

        guests_event = e.get("guests") or []
        guests_project = e.get("projectGuests") or []
        guests_event_ids = sorted([g["id"] for g in guests_event if "id" in g])
        guests_project_ids = sorted([g["id"] for g in guests_project if "id" in g])

        # Salva o estado atual
        new_state[key] = {
            "guests": guests_event_ids,
            "projectGuests": guests_project_ids
        }

        # Determina novidades
        old_guests = set(last_state.get(key, {}).get("guests", []))
        new_guests = set(guests_event_ids)
        old_project_guests = set(last_state.get(key, {}).get("projectGuests", []))
        new_project_guests = set(guests_project_ids)

        new_guests_only = new_guests - old_guests
        new_project_guests_only = new_project_guests - old_project_guests

        # Cria cópia para notificação
        event_copy = e.copy()

        # Adiciona nomes e marca *NEW* apenas para novidades
        for g in (event_copy.get("guests") or []):
            cid = g["id"]
            if cid in celeb_map:
                g["name"] = celeb_map[cid]["name"]
                if cid in new_guests_only:
                    g["name"] += " *NEW*"

        for g in (event_copy.get("projectGuests") or []):
            cid = g["id"]
            if cid in celeb_map:
                g["name"] = celeb_map[cid]["name"]
                if cid in new_project_guests_only:
                    g["name"] += " *NEW*"

        # Se houver novidades, adiciona à lista de notificação
        if new_guests_only or new_project_guests_only:
            new_events.append(event_copy)

    if new_events:
        organized = organize_events(new_events)
        message = format_message(organized)
        send_telegram(message)
        send_discord(message)
        print("Notificação enviada.")
    else:
        print("Sem novidades.")

    # 🔑 Sempre salva o estado atualizado
    save_last_state(new_state)

if __name__ == "__main__":
    main()
