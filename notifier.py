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

# Define o intervalo de datas
START_FILTER = datetime(2025, 10, 5)
END_FILTER = datetime(2025, 10, 14)

# --- FUNÇÕES ---
def get_data(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def load_last_state():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_last_state(state):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def parse_day_str(day_str):
    """Ex: 'Mon, Oct 06' -> datetime"""
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

        guests_event = [g.get("name") for g in e.get("guests", [])] if e.get("guests") else []
        guests_project = [g.get("name") for g in e.get("projectGuests", [])] if e.get("projectGuests") else []

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
                guest_str = []
                if guests_dict.get("guests_event"):
                    guest_str.append("Evento: " + ", ".join(guests_dict["guests_event"]))
                if guests_dict.get("guests_project"):
                    guest_str.append("Projeto: " + ", ".join(guests_dict["guests_project"]))
                guest_str = " | ".join(guest_str) if guest_str else "Nenhum guest listado"
                msg_lines.append(f"    {hour} → {guest_str}")
        msg_lines.append("")  # linha em branco entre dias
    return "\n".join(msg_lines)

def send_telegram(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    else:
        print("[MOCK TELEGRAM] Mensagem:")
        print(message)

def send_discord(message):
    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
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
        # Remove 'Z' e converte para formato UTC padronizado
        if not hour:
            return "unknown"
        h = hour.replace('Z', '')
        try:
            # Tenta converter para datetime e volta para isoformat sem microsegundos
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

        new_state[key] = {
            "guests": guests_event_ids,
            "projectGuests": guests_project_ids
        }

        notify_event = False
        event_copy = e.copy()

        if key not in last_state:
            # Evento totalmente novo (mesmo sem guests)
            notify_event = True
        else:
            old_guests = set(last_state[key].get("guests", []))
            new_guests = set(guests_event_ids)
            old_project_guests = set(last_state[key].get("projectGuests", []))
            new_project_guests = set(guests_project_ids)

            if new_guests - old_guests or new_project_guests - old_project_guests:
                notify_event = True
                # Filtra apenas novos guests
                event_copy["guests"] = [g for g in guests_event if g["id"] in (new_guests - old_guests)]
                event_copy["projectGuests"] = [g for g in guests_project if g["id"] in (new_project_guests - old_project_guests)]

        if notify_event:
            # Substitui IDs por nomes usando celeb_map
            for guest_type in ["guests", "projectGuests"]:
                if event_copy.get(guest_type):
                    for g in event_copy[guest_type]:
                        cid = g["id"]
                        if cid in celeb_map:
                            g["name"] = celeb_map[cid]["name"]
            new_events.append(event_copy)

    if new_events:
        organized = organize_events(new_events)
        message = format_message(organized)
        send_telegram(message)
        send_discord(message)
        save_last_state(new_state)
        print("Notificação enviada.")
    else:
        print("Sem novidades.")

if __name__ == "__main__":
    main()
