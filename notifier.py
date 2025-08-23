import requests
import json
import os

# --- CONFIGURAÇÃO ---
HOMEPAGE_URL = "https://prod-tickets.1iota.com/api/homepage"
CELEB_LIST_URL = "https://prod-tickets.1iota.com/api/celeb/list"
PROJECT_URL = "https://prod-tickets.1iota.com/api/project/{}"  # {id} = show id
LAST_FILE = "last_events.txt"

# TELEGRAM
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# DISCORD
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- FUNÇÕES ---
def get_data():
    resp = requests.get(HOMEPAGE_URL)
    resp.raise_for_status()
    return resp.json()

def get_celeb_list():
    resp = requests.get(CELEB_LIST_URL)
    resp.raise_for_status()
    return resp.json()

def get_show_details(show_id):
    resp = requests.get(PROJECT_URL.format(show_id))
    resp.raise_for_status()
    data = resp.json()
    # Pode não ter date/location
    date = data.get("dateTime", "Data não disponível")
    location = data.get("locationName", "Local não disponível")
    return date, location

def load_last_events():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            data = {}
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" | ")
                show_id = parts[0]
                guests = parts[1].split(",") if len(parts) > 1 else []
                data[show_id] = guests
            return data
    return {}

def save_last_events(events_dict):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        for show_id, guests in events_dict.items():
            f.write(f"{show_id} | {','.join(guests)}\n")

def filter_ny_events(home_data, celeb_data):
    celeb_map = {c['id']: c for c in celeb_data if c['isActive']}
    alerts = {}
    for section in home_data.get("pageSections", []):
        for item in section.get("items", []):
            if 125 not in item.get("projectLocations", []):  # 125 = NY
                continue
            show_id = str(item.get("id"))
            show_title = item.get("title", "Evento sem nome")
            guest_names = []

            # Se homepage já tiver altText
            if item.get("altText"):
                guest_names.append(item["altText"])

            # Checar celeb list
            for celeb in celeb_data:
                if celeb.get("projects") and int(show_id) in celeb["projects"]:
                    guest_names.append(celeb["name"])

            guest_names = sorted(list(set(guest_names)))  # remover duplicatas
            if not guest_names:
                guest_names = ["Sem guests listados ainda"]

            # Pegar data e local
            date, location = get_show_details(show_id)

            alerts[show_id] = {
                "title": show_title,
                "guests": guest_names,
                "date": date,
                "location": location
            }
    return alerts

def send_telegram(messages):
    for msg in messages:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )

def send_discord(messages):
    for msg in messages:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": msg}
        )

# --- EXECUÇÃO ---
def main():
    home_data = get_data()
    celeb_data = get_celeb_list()
    current_events = filter_ny_events(home_data, celeb_data)
    last_events = load_last_events()

    messages = []

    for show_id, info in current_events.items():
        last_guests = last_events.get(show_id, [])
        new_guests = [g for g in info["guests"] if g not in last_guests]
        # Se show novo
        if show_id not in last_events:
            messages.append(
                f"🆕 Novo show em NY: {info['title']}\n"
                f"Data/Horário: {info['date']}\n"
                f"Local: {info['location']}\n"
                f"Guests: {', '.join(info['guests'])}"
            )
        # Se houver guests novos em show existente
        elif new_guests:
            messages.append(
                f"✨ Novos guests no show {info['title']}:\n"
                f"{', '.join(new_guests)}\n"
                f"Data/Horário: {info['date']}\n"
                f"Local: {info['location']}"
            )

    if messages:
        # Enviar para Telegram e Discord simultaneamente
        send_telegram(messages)
        send_discord(messages)
    else:
        print("Sem novidades.")

    # Atualiza o arquivo
    new_last = {show_id: info["guests"] for show_id, info in current_events.items()}
    save_last_events(new_last)

if __name__ == "__main__":
    main()
