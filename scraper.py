import requests
from bs4 import BeautifulSoup
import json
import os
import asyncio
from telegram import Bot
import schedule
import time

# ── Load config ──────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)

BOT_TOKEN  = config["BOT_TOKEN"]
CHAT_ID    = config["CHAT_ID"]
KEYWORDS   = [k.lower() for k in config["keywords"]]
LOCATION   = config["location"].lower()
SEEN_FILE  = "seen_jobs.json"

# ── Seen jobs store ──────────────────────────────────────────
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# ── Scraper (fixed selectors) ─────────────────────────────────
def scrape_internshala(keyword):
    jobs = []
    url = f"https://internshala.com/internships/{keyword}-internship"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.find_all("div", class_="individual_internship")

        for card in cards:
            try:
                # ── Job ID (unique per listing) ──
                job_id = card.get("id", "")  # e.g. "individual_internship_3095275"

                # ── Title ──
                title_tag = card.find("a", class_="job-title-href")
                title = title_tag.text.strip() if title_tag else "N/A"

                # ── Link ──
                href = card.get("data-href", "")
                link = "https://internshala.com" + href if href else ""

                # ── Company ──
                company_tag = card.find("p", class_="company-name")
                company = company_tag.text.strip() if company_tag else "N/A"

                # ── Location ──
                location_tag = card.find("div", class_="locations")
                location = location_tag.text.strip() if location_tag else "N/A"

                # ── Stipend ──
                stipend_tag = card.find("span", class_="stipend")
                stipend = stipend_tag.text.strip() if stipend_tag else "N/A"

                # ── Duration ──
                spans = card.find_all("span")
                duration = "N/A"
                for span in spans:
                    text = span.text.strip()
                    if "Month" in text or "Week" in text:
                        duration = text
                        break

                if not job_id:
                    continue

                jobs.append({
                    "id":       job_id,
                    "title":    title,
                    "company":  company,
                    "location": location,
                    "stipend":  stipend,
                    "duration": duration,
                    "link":     link,
                    "source":   "Internshala"
                })

            except Exception as e:
                continue

    except Exception as e:
        print(f"  Error scraping '{keyword}': {e}")

    return jobs

# ── Location filter ───────────────────────────────────────────
def is_relevant(job):
    if not LOCATION:
        return True
    loc = job["location"].lower()
    return LOCATION in loc or "remote" in loc or "work from home" in loc

# ── Telegram alert ────────────────────────────────────────────
async def send_alert(job):
    bot = Bot(token=BOT_TOKEN)
    message = (
        f"*New Internship Found!*\n\n"
        f"*{job['title']}*\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"💰 {job['stipend']}\n"
        f"🗓 {job['duration']}\n\n"
        f"[Apply on Internshala]({job['link']})"
    )
    await bot.send_message(
        chat_id=CHAT_ID,
        text=message,
        parse_mode="Markdown"
    )

async def send_summary(new_count, total_checked):
    bot = Bot(token=BOT_TOKEN)
    msg = (
        f"*Daily Scan Complete*\n"
        f"Checked: {total_checked} listings\n"
        f"New matches: {new_count}\n"
    )
    if new_count == 0:
        msg += "_No new listings since last run._"
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

# ── Main run ──────────────────────────────────────────────────
def run_bot():
    print("Running job scan...")
    seen = load_seen()
    all_jobs = []

    for keyword in KEYWORDS:
        keyword_slug = keyword.replace(" ", "-")
        jobs = scrape_internshala(keyword_slug)
        all_jobs.extend(jobs)
        print(f"  [{keyword}] Found {len(jobs)} listings")

    new_jobs = []
    for job in all_jobs:
        if job["id"] not in seen and is_relevant(job):
            new_jobs.append(job)
            seen.add(job["id"])

    for job in new_jobs:
        asyncio.run(send_alert(job))
        print(f"  Alerted: {job['title']} @ {job['company']}")
        time.sleep(1)

    asyncio.run(send_summary(len(new_jobs), len(all_jobs)))
    save_seen(seen)
    print(f"Done. {len(new_jobs)} new jobs alerted.")

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    print("Bot started. First run happening now...")
    run_bot()

    schedule.every().day.at("09:00").do(run_bot)
    print("Scheduled daily at 9:00 AM. Keep this terminal open.")

    while True:
        schedule.run_pending()
        time.sleep(60)