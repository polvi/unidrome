#!/usr/bin/env python3
"""Generate a ForeFlight KML layer of Canadian airports where you can clear
customs flying a (general aviation) aircraft into Canada.

Source: CBSA "Directory of CBSA Offices and Services" single-page app.

  - List of all offices (coords + service IDs):
        /api/initial-load?lang=en
  - Per-office detail (ICAO code, address, hours, phone, clearance limit):
        /api/office?id=<office number>&lang=en

Each office carries a list of numeric service IDs; the air "Airport of Entry"
(AOE) services tell us where aircraft can be cleared. We keep the ones a GA
pilot can actually use and drop military-only / cargo-only sites, then enrich
each with its detail page.
"""

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

API_BASE = "https://do-rb.cbsa-asfc.cloud-nuage.canada.ca/api/"
HOME = "https://do-rb.cbsa-asfc.cloud-nuage.canada.ca/?lang=en_CA"
CACHE = "data/ca/cbsa/initial-load.json"
DETAIL_DIR = "data/ca/cbsa/offices"
OUTPUT = "build/CA_AOE.kml"  # gitignored build dir; seed input for the worker

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": HOME,
    "X-Requested-With": "XMLHttpRequest",
}

# The site sits behind a WAF that 403s bursts of requests. Use one cookie-backed
# session, fetch sequentially with a small delay, and back off on blocks.
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _open(url, headers=None):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with _opener.open(req, timeout=60) as resp:
        return resp.read()

# Air-mode Airport of Entry services a general-aviation pilot can use to clear
# customs, mapped to a short note. Service IDs come from the feed's `services`
# table. Military-only (37, AOE/M) and cargo-only (40, AOE/CARGO) are excluded
# on purpose -- add them here if you want them on the layer.
AOE_SERVICES = {
    5:       "AOE: all scheduled/unscheduled aircraft",
    30:      "AOE/CAN: CANPASS private/corporate members only",
    44:      "AOE/15/SEAPL: seaplane, unscheduled, ≤15 incl crew, prior CBSA approval",
    45:      "AOE/CAN/SEAPL: seaplane, CANPASS members only",
    1703937: "AOE/15: general aviation, unscheduled, ≤15 incl crew, prior CBSA approval",
    1802248: "AOE/SEASONAL: all aircraft, seasonal hours",
}


def get_json(url, tries=5):
    """GET with backoff; retries WAF blocks (403) and transient errors."""
    delay = 8
    for attempt in range(tries):
        try:
            raw = _open(url)
            if raw.lstrip()[:1] in (b"{", b"["):
                return raw
        except Exception:
            pass
        if attempt < tries - 1:
            _open(HOME, headers={"User-Agent": HEADERS["User-Agent"]})  # re-prime
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"failed after {tries} tries: {url}")


def fetch_once(number):
    """One attempt at a detail page. Returns ('ok', detail) | ('block', None)
    [WAF 403] | ('err', None) [backend 400 / flaky]. The endpoint is heavily
    rate-limited, so callers retry across passes rather than hammering."""
    try:
        raw = _open(API_BASE + f"office?id={number}&lang=en")
    except urllib.error.HTTPError as e:
        return ("block", None) if e.code == 403 else ("err", None)
    except Exception:
        return ("err", None)
    if raw.lstrip()[:1] != b"{" or b'"Error"' in raw[:40]:
        return ("err", None)
    try:
        detail = json.loads(raw)
    except Exception:
        return ("err", None)
    os.makedirs(DETAIL_DIR, exist_ok=True)
    with open(os.path.join(DETAIL_DIR, f"{number}.json"), "wb") as f:
        f.write(raw)
    return ("ok", detail)


def drain(offices, passes=40, delay=12):
    """Patiently fill the per-office detail cache, resumable across runs.

    Rate limit is strict, so we make many slow passes: one quick attempt per
    uncached office per pass, backing off hard on WAF blocks. Re-run anytime;
    cached offices are skipped."""
    todo = [o for o in offices
            if not os.path.exists(os.path.join(DETAIL_DIR, f"{o['number']}.json"))]
    print(f"drain: {len(todo)} offices need detail")
    for p in range(passes):
        if not todo:
            break
        try:
            _open(HOME, headers={"User-Agent": HEADERS["User-Agent"]})
        except Exception:
            pass
        still = []
        got = 0
        for o in todo:
            st, _ = fetch_once(o["number"])
            if st == "ok":
                got += 1
            else:
                still.append(o)
                time.sleep(60 if st == "block" else 0)
            time.sleep(delay)
        todo = still
        print(f"  pass {p+1}: +{got} cached, {len(todo)} remaining")
        if got == 0:
            time.sleep(120)  # everything blocked this pass; rest before retrying
    print(f"drain done: {len(todo)} still missing")


def load_data():
    """Fetch the office list (or use a local cache), saving a fresh copy."""
    try:
        raw = get_json(API_BASE + "initial-load?lang=en")
        data = json.loads(raw)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "wb") as f:
            f.write(raw)
        print(f"Fetched office list ({len(raw)} bytes), cached to {CACHE}")
    except Exception as e:
        print(f"Fetch failed ({e}); falling back to cache {CACHE}")
        with open(CACHE) as f:
            data = json.load(f)
    return data


def load_detail(number):
    """Return cached per-office detail, or {} if not yet fetched."""
    path = os.path.join(DETAIL_DIR, f"{number}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def fmt_address(detail):
    for a in detail.get("address") or []:
        if a.get("type") == "PHYSICAL" or len(detail.get("address", [])) == 1:
            parts = [a.get("streetEn1", "").strip(),
                     a.get("cityEn", "").strip(),
                     f"{a.get('province','').strip()} {a.get('postalCode','').strip()}".strip()]
            return ", ".join(p for p in parts if p)
    return ""


def fmt_hours(detail):
    lines = []
    for block in detail.get("hours") or []:
        label = block.get("labelEn", "").strip()
        slots = []
        for oh in block.get("officeHours") or []:
            day = oh.get("labelEn", "").strip()
            if oh.get("customEn"):
                t = oh["customEn"].strip()
            elif oh.get("start") or oh.get("end"):
                t = f"{oh.get('start','').strip()}-{oh.get('end','').strip()}"
            else:
                t = ""
            slots.append(" ".join(p for p in (day, t) if p))
        if slots:
            lines.append(f"{label}: " + "; ".join(slots) if label else "; ".join(slots))
    return lines


def fmt_phone(detail):
    return [f"{p.get('labelEn','Phone').strip()}: {p.get('value','').strip()}"
            for p in detail.get("phone") or [] if p.get("value")]


def build_airport(o, detail):
    code_note = {sid: note for sid, note in AOE_SERVICES.items()}
    matched = [s for s in o.get("services", []) if s in AOE_SERVICES]
    limits = {a.get("aoeNumber"): a.get("clearanceLimit")
              for a in detail.get("airportOfEntry") or []}
    notes = []
    for sid in matched:
        note = code_note[sid]
        if limits.get(sid):
            note += f" (clearance limit {limits[sid]})"
        notes.append(note)
    return {
        "name": detail.get("name") or o["name"],
        "number": o["number"],
        "icao": (detail.get("airportCode") or "").strip(),
        "province": o.get("province", ""),
        "lat": o["latitude"],
        "lon": o["longitude"],
        "codes": [AOE_SERVICES[s].split(":")[0] for s in matched],
        "notes": notes,
        "address": fmt_address(detail),
        "hours": fmt_hours(detail),
        "phones": fmt_phone(detail),
    }


def esc(s):
    """Escape text for safe inclusion in an HTML/CDATA description."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def description_html(apt):
    """Clean basic HTML for a placemark description (ForeFlight supports text +
    links, line breaks, headings, font color/size -- guide §25.8.3.1)."""
    head = f"<b>{esc(apt['name'])}</b>"
    if apt["icao"]:
        head += f" ({esc(apt['icao'])})"
    sub = esc(apt["address"] or apt["province"])
    # each "<br/>"-prefixed entry renders as a blank line then that line
    parts = [head, sub, "<br/><b>Designation</b>"]
    parts += [esc(n) for n in apt["notes"]]
    if apt["hours"]:
        hrs = [esc(h) for h in apt["hours"]]
        parts += ["<br/><b>Hours</b>"] + hrs
    if apt["phones"]:
        phones = [esc(p) for p in apt["phones"]]
        parts += ["<br/>" + phones[0]] + phones[1:]
    parts.append(
        f'<br/><a href="https://do-rb.cbsa-asfc.cloud-nuage.canada.ca/'
        f'?lang=en_CA&amp;id={apt["number"]}">CBSA office page</a>')
    return "<br/>".join(parts)


def main():
    data = load_data()

    offices = []
    for o in data["offices"]:
        if not o.get("publishedExternal", True):
            continue
        if o.get("latitude") is None or o.get("longitude") is None:
            continue
        if not any(s in AOE_SERVICES for s in o.get("services", [])):
            continue
        offices.append(o)

    # `drain` mode slowly fills the detail cache from the rate-limited API;
    # the default build just uses whatever detail is already cached.
    if "drain" in sys.argv:
        drain(offices)

    airports = [build_airport(o, load_detail(o["number"])) for o in offices]

    # Build KML
    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element(f"{{{kml_ns}}}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "Canada Airports of Entry (CBSA)"

    # ElementTree can't emit CDATA, so descriptions get a unique token here and
    # the token is swapped for a <![CDATA[...]]> HTML block after serialization.
    descriptions = {}
    for apt in sorted(airports, key=lambda a: (a["province"], a["name"])):
        pm = ET.SubElement(doc, "Placemark")
        title = apt["name"]
        if apt["icao"]:
            title += f" ({apt['icao']})"
        ET.SubElement(pm, "name").text = title

        token = f"@@DESC{len(descriptions)}@@"
        descriptions[token] = description_html(apt)
        ET.SubElement(pm, "description").text = token

        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "coordinates").text = f"{apt['lon']},{apt['lat']},0"

    ET.indent(ET.ElementTree(kml))
    xml = ET.tostring(kml, encoding="unicode")
    for token, html in descriptions.items():
        xml = xml.replace(token, f"<![CDATA[{html}]]>")
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
        f.write(xml)
    n_icao = sum(1 for a in airports if a["icao"])
    print(f"Wrote {len(airports)} Canadian AOE airports to {OUTPUT} "
          f"({n_icao} with ICAO codes)")


if __name__ == "__main__":
    main()
