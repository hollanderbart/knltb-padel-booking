"""
Integratietest voor het KNLTB Padel Booking script.

Vereisten:
  - KNLTB_EMAIL en KNLTB_PASSWORD in omgeving of .env bestand
  - Playwright Chromium geïnstalleerd (playwright install chromium)

Uitvoeren:
  pytest test_integration.py -v -s
  pytest test_integration.py -v -s --headed
"""

import re
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from booking import PadelBooker

# Laad .env zodat credentials beschikbaar zijn
load_dotenv()


def _find_any_available_slot(page, booker: PadelBooker) -> dict | None:
    """
    Zoek flexibel een beschikbaar indoor slot bij een van de gevonden clubs
    in de komende 7 dagen, zonder beperking op tijdvenster of dagdeel.

    Returns:
        Dict met slot-info of None als er geen beschikbaar slot is.
    """
    import os

    # Gebruik de clubs uit de config-locatie
    city = booker.config["location"]["city"]
    radius = str(booker.config["location"]["radius_km"])

    from booking import SEARCH_URL

    for day_offset in range(7):
        date = datetime.now() + timedelta(days=day_offset)
        date_str = date.strftime("%d-%m-%Y")

        page.goto(SEARCH_URL, wait_until="load", timeout=30000)
        page.wait_for_timeout(1500)
        booker._accept_cookies(page)

        # Sport: Padel
        page.locator("select#sportId").select_option("2")
        page.wait_for_timeout(1500)

        # Locatie
        loc_input = page.locator("input#location")
        loc_input.fill(city)
        loc_input.blur()
        page.wait_for_timeout(2500)

        # Afstand
        page.locator("select#distance").select_option(radius)
        page.wait_for_timeout(1500)

        # Daktype: binnen
        page.locator("select#indoor").select_option("INDOOR")
        page.wait_for_timeout(1500)

        # Datum instellen via Livewire
        lw_match = re.search(
            r"window\.Livewire\.find\('([^']+)'\)\.set\('date'", page.content()
        )
        if lw_match:
            page.evaluate(
                f"window.Livewire.find('{lw_match.group(1)}').set('date', '{date_str}')"
            )
            page.wait_for_timeout(2000)

        # Clubs ophalen
        cards = page.locator(".c-club-card.mp-club-card")
        count = cards.count()

        for club_idx in range(count):
            card = cards.nth(club_idx)
            try:
                name = card.locator("h3").first.inner_text().strip()
                book_url = card.locator("a.mp-cta-link").first.get_attribute("href") or ""
                address = card.locator(".c-club-card__address").first.inner_text().strip()
            except Exception:
                continue

            if not book_url:
                continue

            club = {"name": name, "address": address, "url": book_url}

            # Navigeer naar clubpagina
            page.goto(club["url"], wait_until="load", timeout=30000)
            page.wait_for_timeout(1500)
            booker._accept_cookies(page)

            # Sport: Padel
            sport_select = page.locator("select#sportId")
            if sport_select.count() > 0:
                sport_select.select_option("2")
                page.wait_for_timeout(1500)

            # Daktype: binnen
            indoor_select = page.locator("select#indoor")
            if indoor_select.count() > 0:
                indoor_select.select_option("INDOOR")
                page.wait_for_timeout(1500)

            # Dagdeel: leeg (alle tijden) — geen filter instellen

            # Datum instellen via Livewire
            lw_match = re.search(
                r"window\.Livewire\.find\('([^']+)'\)\.set\('date'", page.content()
            )
            if lw_match:
                page.evaluate(
                    f"window.Livewire.find('{lw_match.group(1)}').set('date', '{date_str}')"
                )
                page.wait_for_timeout(2000)

            # Haal tijdsloten op
            slots = page.locator(".timeslot-container a.timeslot")

            for i in range(slots.count()):
                slot = slots.nth(i)

                # Court type label ophalen
                try:
                    label = slot.evaluate("""el => {
                        let s = el.closest('.timeslots');
                        return s && s.previousElementSibling ? s.previousElementSibling.innerText : '';
                    }""").lower()
                except Exception:
                    label = ""

                # Skip buiten-banen
                if "buiten" in label:
                    continue

                # Eerste beschikbare slot gevonden
                try:
                    time_text = slot.locator(".timeslot-time").first.inner_text().strip()
                except Exception:
                    time_text = "onbekend"

                try:
                    court_name = slot.locator(".timeslot-name").first.inner_text().strip()
                    court_name = court_name.split("\n")[0].strip()
                except Exception:
                    court_name = "Onbekende baan"

                slot_id = slot.get_attribute("id") or ""

                return {
                    "slot_id": slot_id,
                    "court_name": court_name,
                    "time_range": time_text.replace("\n", " "),
                    "club_name": club["name"],
                    "club_address": club["address"],
                    "date_str": date_str,
                }

    return None


def test_full_booking_flow(headed):
    """
    End-to-end integratietest die de volledige boekingsflow doorloopt:
    inloggen, clubs zoeken, een slot vinden en doorboeken tot de betalingspagina.
    """
    import os

    # Stap 1: credentials checken
    email = os.getenv("KNLTB_EMAIL", "").strip()
    password = os.getenv("KNLTB_PASSWORD", "").strip()

    if not email or not password:
        pytest.skip(
            "KNLTB_EMAIL en/of KNLTB_PASSWORD niet gevonden in omgeving of .env — test overgeslagen"
        )

    # Stap 2: PadelBooker instantiëren
    booker = PadelBooker("config.yaml")

    browser = None
    context = None

    with sync_playwright() as pw:
        booker._playwright = pw

        # Stap 3: browser en context openen
        browser = pw.chromium.launch(headless=not headed)
        context = booker._make_context(browser, headed)
        context = booker._ensure_logged_in(browser, context, headed)

        try:
            # Stap 4: nieuwe pagina
            page = context.new_page()

            # Stap 5: clubs zoeken
            clubs = booker._search_clubs(page)
            assert len(clubs) > 0, (
                "Geen clubs gevonden — controleer config.yaml (locatie/filters) "
                "en of de website bereikbaar is"
            )

            # Stap 6: flexibel slot zoeken in komende 7 dagen
            slot_info = _find_any_available_slot(page, booker)
            assert slot_info is not None, (
                "Geen enkel beschikbaar indoor slot gevonden in de komende 7 dagen "
                "bij alle gevonden clubs"
            )

            # Stap 7: monkeypatch wachttijden (> 3000ms → 1000ms)
            original_wait = page.wait_for_timeout
            page.wait_for_timeout = lambda ms: original_wait(min(ms, 1000))

            # Stap 8: boeken
            success = booker._book_timeslot(page, slot_info)
            assert success is True, (
                f"_book_timeslot gaf False terug voor slot {slot_info['slot_id']} "
                f"bij {slot_info['club_name']}"
            )

            # Meetandplay gebruikt /reserveren als winkelwagen/checkout URL
            payment_keywords = ["payment", "checkout", "betaling", "betalen", "order", "bestelling", "reserveren", "winkelwagen"]
            assert any(kw in page.url for kw in payment_keywords) or "Winkelwagen" in page.content(), (
                f"Niet op betalingspagina beland — huidige URL: {page.url}"
            )

        finally:
            # Stap 9: teardown
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

        booker._playwright = None
