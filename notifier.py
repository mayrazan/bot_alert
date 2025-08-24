import requests
import json
import os
from collections import defaultdict
from datetime import datetime

# --- CONFIGURAÇÃO ---
EVENTS_URL = "https://prod-tickets.1iota.com/api/event/list"
CELEBS_URL = "https://prod-tickets.1iota.com/api/celeb/list"
LAST_FILE = "last_news.json"

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DISCORD
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Define o intervalo
start_filter = datetime(2025, 10, 5)
end_filter = datetime(2025, 10, 14)

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
    # Ex: "Mon, Oct 06" -> datetime
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
        if not day_str:
            continue

        day_dt = parse_day_str(day_str)
        if not day_dt or not (start_filter <= day_dt <= end_filter):
            continue

        show = e.get("title", "Show sem título")
        hour = e.get("when", "Horário não informado")

        # Separar guests de evento e do projeto
        guests_event = [g.get("name") for g in e.get("guests", [])] if e.get("guests") else []
        guests_project = [g.get("name") for g in e.get("projectGuests", [])] if e.get("projectGuests") else []

        organized[day_dt][show][hour] = {
            "guests_event": guests_event,
            "guests_project": guests_project
        }

    # ordenar por data real
    organized_sorted = dict(sorted(organized.items()))
    return organized_sorted


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

def send_discord(message):
    print(message)
    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

def main():
    events = get_data(EVENTS_URL)
    celebs = get_data(CELEBS_URL)
    celeb_map = {c["id"]: c for c in celebs if c.get("isActive")}

    last_state = load_last_state()
    new_state = {}
    new_events = []

    for e in events:
        eid = str(e["eventId"])
        hour = e.get("when") or e.get("startDateUtc") or "unknown"
        key = f"{eid}_{hour}"

        # IDs dos guests de evento e do projeto
        guests_event_ids = [g["id"] for g in e.get("guests", [])] if e.get("guests") else []
        guests_project_ids = [g["id"] for g in e.get("projectGuests", [])] if e.get("projectGuests") else []

        new_state[key] = {
            "guests": guests_event_ids,
            "projectGuests": guests_project_ids
        }

        notify_event = False
        event_copy = e.copy()

        if key not in last_state:
            # Evento novo completo
            notify_event = True
        else:
            # Checa se há guests novos
            old_guests = set(last_state[key].get("guests", []))
            new_guests = set(guests_event_ids)
            old_project_guests = set(last_state[key].get("projectGuests", []))
            new_project_guests = set(guests_project_ids)

            if new_guests - old_guests or new_project_guests - old_project_guests:
                notify_event = True
                # Filtra apenas novos guests
                event_copy["guests"] = [g for g in e.get("guests", []) if g["id"] in (new_guests - old_guests)]
                event_copy["projectGuests"] = [g for g in e.get("projectGuests", []) if g["id"] in (new_project_guests - old_project_guests)]

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
        print("Notificação enviada.")
    else:
        print("Sem novidades.")

    save_last_state(new_state)

if __name__ == "__main__":
    main()
