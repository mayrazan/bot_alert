import requests
import json
import os
from collections import defaultdict

# --- CONFIGURAÇÃO ---
EVENTS_URL = "https://prod-tickets.1iota.com/api/event/list"
CELEBS_URL = "https://prod-tickets.1iota.com/api/celeb/list"
LAST_FILE = "last_news.json"

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
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_last_state(state):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def organize_events(events):
    """
    Agrupa eventos por dia → show → hora → guests
    """
    organized = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for e in events:
        day = e.get("localStartDay", "Data desconhecida")
        show = e.get("title", "Show sem título")
        hour = e.get("when", "Horário não informado")
        guests = [g.get("name") for g in e.get("guests", [])] if e.get("guests") else []
        organized[day][show][hour].extend(guests)
    return organized

def format_message(organized_events):
    msg_lines = []
    for day, shows in sorted(organized_events.items()):
        msg_lines.append(f"*{day}*")
        for show, times in shows.items():
            msg_lines.append(f"  {show}:")
            for hour, guests in times.items():
                guest_str = ", ".join(guests) if guests else "Nenhum guest listado"
                msg_lines.append(f"    {hour} → {guest_str}")
        msg_lines.append("")  # linha em branco entre dias
    return "\n".join(msg_lines)

def send_telegram(message):
    print(message)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def send_discord(message):
    print(message)
    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

# --- EXECUÇÃO ---
def main():
    events = get_data(EVENTS_URL)
    celebs = get_data(CELEBS_URL)
    celeb_map = {c["id"]: c for c in celebs if c.get("isActive")}

    last_state = load_last_state()
    new_state = {}
    new_events = []

    for e in events:
        # Chave única por evento + horário
        eid = str(e["eventId"])
        hour = e.get("when") or e.get("startDateUtc") or "unknown"
        key = f"{eid}_{hour}"

        guests_ids = [g["id"] for g in e.get("guests", [])] if e.get("guests") else []

        new_state[key] = guests_ids

        notify_event = False
        event_copy = e.copy()

        if key not in last_state:
            # Evento novo completo
            notify_event = True
        else:
            # Checa se há guests novos
            old_guests = set(last_state[key])
            new_guests = set(guests_ids)
            if new_guests - old_guests:
                notify_event = True
                # Filtra apenas guests novos
                event_copy["guests"] = [g for g in e.get("guests", []) if g["id"] in (new_guests - old_guests)]

        if notify_event:
            # Substitui IDs por nomes usando celeb_map
            if event_copy.get("guests"):
                for g in event_copy["guests"]:
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
