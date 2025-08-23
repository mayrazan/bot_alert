import requests
import json
import os
from collections import defaultdict

# --- CONFIGURAÇÃO ---
EVENTS_URL = "https://prod-tickets.1iota.com/api/event/list"
CELEBS_URL = "https://prod-tickets.1iota.com/api/celeb/list"
LAST_FILE = "last_events.json"

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

def load_last_events():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_last_events(data):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def organize_events(events):
    """
    Agrupa os eventos por dia, depois por show, depois lista horário e guests.
    Retorna um dict: {dia: {show: {hora: [guests]}}}
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
    """
    Transforma o dict em texto legível para Telegram/Discord.
    """
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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def send_discord(message):
    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

# --- EXECUÇÃO ---
def main():
    events = get_data(EVENTS_URL)
    celebs = get_data(CELEBS_URL)

    last_state = load_last_events()

    # Criar um mapeamento rápido de eventos por id
    new_state = {}
    new_events = []
    for e in events:
        eid = str(e["eventId"])
        guests_ids = [g["id"] for g in e.get("guests", [])] if e.get("guests") else []
        new_state[eid] = guests_ids

        if eid not in last_state:
            # novo evento completo
            new_events.append(e)
        else:
            # checa se houve guest novo
            old_guests = set(last_state[eid])
            new_guests = set(guests_ids)
            if new_guests - old_guests:
                # adiciona evento mas filtra só os guests novos
                e_copy = e.copy()
                e_copy["guests"] = [g for g in e.get("guests", []) if g["id"] in (new_guests - old_guests)]
                new_events.append(e_copy)

    if new_events:
        organized = organize_events(new_events)
        message = format_message(organized)
        send_telegram(message)
        send_discord(message)
        save_last_events(new_state)
    else:
        print("Sem novidades.")

if __name__ == "__main__":
    main()
