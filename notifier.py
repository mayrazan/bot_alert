import requests
import json
import os

# --- CONFIGURAÇÃO ---
HOMEPAGE_URL = "https://prod-tickets.1iota.com/api/homepage"
LAST_FILE = "last_events.txt"

# Escolher envio: 'telegram' ou 'discord'
PLATAFORMA = "telegram"

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DISCORD
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- FUNÇÕES ---
def get_data():
    response = requests.get(HOMEPAGE_URL)
    response.raise_for_status()
    return response.json()

def load_last_events():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    return set()

def save_last_events(events):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        for event in events:
            f.write(event + "\n")

def filter_ny_events(data):
    alerts = []
    for section in data.get("pageSections", []):
        for item in section.get("items", []):
            if 125 in item.get("projectLocations", []):  # 125 = NY
                event_name = item.get("title", "Evento sem nome")
                guest_name = item.get("altText", None)
                if guest_name:
                    alerts.append(f"{guest_name} → {event_name}")
                else:
                    alerts.append(f"{event_name}")
    return alerts

def send_telegram(messages):
    for msg in messages:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def send_discord(messages):
    for msg in messages:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

# --- EXECUÇÃO ---
def main():
    data = get_data()
    current_events = set(filter_ny_events(data))
    last_events = load_last_events()

    new_events = current_events - last_events
    if new_events:
        sorted_events = sorted(new_events)
        if PLATAFORMA == "telegram":
            send_telegram(sorted_events)
        elif PLATAFORMA == "discord":
            send_discord(sorted_events)
        save_last_events(current_events)
    else:
        print("Sem novidades.")

if __name__ == "__main__":
    main()
