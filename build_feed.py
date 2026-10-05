#!/usr/bin/env python3
"""Compari.ro feed for Pepiniera României, built from the public /products.json.
Usage: python3 build_feed.py [--fetch]   (--fetch = re-download products.json pages into raw/)"""
import json, re, html, csv, sys, os, glob, time, urllib.request, urllib.parse, urllib.error
from xml.sax.saxutils import escape

BASE = "https://pepinieraromaniei.ro"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CAT_PLANT = "Casa si gradina > Grădină > Planta de gradina decorativa"
CAT_SEED = "Casa si gradina > Grădină > Seminte, bulbi"
CAT_GRASS = "Casa si gradina > Grădină > Seminte de iarba"
MANUFACTURER = "Pepiniera României"
FREE_SHIP_FROM = 299.0
SHIP_COST = "24.90"

def get_json(url, tries=8):
    """Shopify returns 429 to busy cloud IPs; retry with growing pauses."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CompariFeedPepiniera/1.0)", "Accept": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1: raise
            wait = int(e.headers.get("Retry-After") or 0) or min(15 * (2 ** i), 240)
            print(f"HTTP {e.code} la {url}, reîncerc peste {wait}s", flush=True)
            time.sleep(wait)

def fetch():
    os.makedirs(RAW, exist_ok=True)
    for f in glob.glob(os.path.join(RAW, "p*.json")): os.remove(f)
    page = 1
    while True:
        data = get_json(f"{BASE}/products.json?limit=250&page={page}")
        if not data["products"]: break
        json.dump(data, open(os.path.join(RAW, f"p{page}.json"), "w"))
        page += 1; time.sleep(5)

def load():
    P = []
    for f in sorted(glob.glob(os.path.join(RAW, "p*.json")), key=lambda x: int(re.findall(r"\d+", os.path.basename(x))[0])):
        P += json.load(open(f))["products"]
    return P

BULB_TYPE = re.compile(r"bulbi|^pachet (crini|lalele|narcise|gladiole|frezie|anemone|bujor)", re.I)
BULB_TITLE = re.compile(r"\bbulb|lalel|bujor|narcis|\bcrini?\b|gladiol|frezi", re.I)

def classify(p):
    """Return (include: bool, reason_or_category)."""
    t, ty = p["title"], (p["product_type"] or "")
    if BULB_TYPE.search(ty) or BULB_TITLE.search(t):
        return False, "bulbi/bujori/lalele (zona Fitza)"
    if ty.lower().startswith("antidaunatori"):
        return False, "antidaunatori (nu sunt plante)"
    s = (t + " " + ty).lower()
    if "gazon" in s:
        return True, CAT_GRASS
    if re.search(r"semin|senimnte", s):
        return True, CAT_SEED
    return True, CAT_PLANT

WORDS = {  # diacritice / greșeli frecvente în titluri
    r"\bBucati\b": "Bucăți", r"\bbucati\b": "bucăți", r"\bBucății\b": "Bucăți", r"\bBucăti\b": "Bucăți",
    r"\bBucata\b": "Bucată", r"\bbucata\b": "bucată", r"\bGradina\b": "Grădină", r"\bgradina\b": "grădină",
    r"\bRuseasca\b": "Rusească", r"\bSeminte\b": "Semințe", r"\bseminte\b": "semințe",
    r"\bVita\b": "Viță", r"\bvita\b": "viță", r"\bButas\b": "Butaș", r"\bbutas\b": "butaș",
    r"\bButasi\b": "Butași", r"\bbutasi\b": "butași", r"\bPromotional\b": "Promoțional",
    r"\bstrguri\b": "struguri", r"\bStrguri\b": "Struguri", r"\bMana Maicii\b": "Mâna Maicii",
    r"\bCires\b": "Cireș", r"\bVisin\b": "Vișin", r"\bPar\b(?=\s+[„\"A-Z])": "Păr", r"\bMar\b(?=\s+[„\"A-Z])": "Măr",
}

OVERRIDES = {  # titluri prea încâlcite pentru reguli
    "Pachet Mixt-3buc- Negru-Viță de vie de masă-Butași": "Pachet mixt viță de vie de masă neagră, butași, 3 bucăți",
    "Salba Japoneza, ''Euonymus  125/150 cm,": "Salbă japoneză „Euonymus”, 125-150 cm",
    "Pachet mix 50 bulbi-29.90 redusi de la 100 lei": "Pachet mix 50 bulbi",
}

def clean_name(t):
    t = html.unescape(t)
    if t in OVERRIDES: return OVERRIDES[t]
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", t)            # emoji
    t = re.sub(r"\s*[-–]?\s*(redus[i]?\s+)?de la\s+\d+([.,]\d+)?\s*(lei)?\s*la\s+\d+([.,]\d+)?\s*lei", "", t, flags=re.I)
    t = re.sub(r"\s*[-–]\s*redus[i]?\b.*$", "", t, flags=re.I)                    # "-redus de la 144 la 59.90 lei"
    t = re.sub(r"\s*[-–]?\s*\d+([.,]\d+)?\s*lei\s+redus[i]?\s+de\s+la\s+\d+([.,]\d+)?\s*lei", "", t, flags=re.I)
    t = re.sub(r"\s*[-–]\s*\d+([.,]\d+)?\s*redus[i]?\s+de\s+la\s+\d+([.,]\d+)?\s*lei", "", t, flags=re.I)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:     # TOT CU MAJUSCULE -> Titlu
        t = " ".join(w if re.fullmatch(r"[A-Z]{1,3}\d*|F1|XL|XXL", w) else w.capitalize() for w in t.lower().split())
        t = re.sub(r"\bMix\b", "Mix", t)
    for a, b in WORDS.items(): t = re.sub(a, b, t)
    t = re.sub(r"\b(promo|promoțional|promotional)\b\s*", "", t, flags=re.I)   # fără reclamă în nume (regulă Compari)
    t = re.sub(r"^(\d+\s+buc)", r"Pachet \1", t, flags=re.I)
    t = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", t)
    t = re.sub(r"\s+,", ",", t); t = re.sub(r"(?<!\d),(?=\S)", ", ", t)
    t = re.sub(r"\s*-\s*(?=\d+\s*buc)", " – ", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–,")
    return t[:1].upper() + t[1:]

def clean_desc(body, n=600):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body or "", flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]", "", s)
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return s

def build():
    P = load()
    rows, excl = [], []
    for p in P:
        avail = [v for v in p["variants"] if v["available"]]
        if not avail:
            excl.append((p, "fără stoc")); continue
        avail = [v for v in avail if float(v["price"]) > 0]
        if not avail:
            excl.append((p, "fără preț")); continue
        ok, cat = classify(p)
        if not ok:
            excl.append((p, cat)); continue
        multi = len({v["price"] for v in avail}) > 1     # rând separat doar dacă prețurile diferă
        for v in (avail if multi else avail[:1]):
            price = float(v["price"])
            img = (v.get("featured_image") or {}).get("src") or (p.get("images") or [{}])[0].get("src", "")
            name = clean_name(p["title"]) + (f" – {v['title']}" if multi and v["title"] != "Default Title" else "")
            url = f"{BASE}/products/{urllib.parse.quote(p['handle'])}" + (f"?variant={v['id']}" if multi else "")
            rows.append({
                "Identifier": str(v["id"]),
                "Manufacturer": MANUFACTURER,
                "Name": name,
                "Category": cat,
                "ProductUrl": url,
                "Price": f"{price:.2f}",
                "ProductNumber": v.get("sku") or "",
                "Description": clean_desc(p.get("body_html")),
                "ImageUrl": img.split("?")[0] if img else "",
                "DeliveryCost": "FREE" if price >= FREE_SHIP_FROM else SHIP_COST,
                "_title": p["title"], "_type": p["product_type"],
            })
    return P, rows, excl

FIELDS = ["Identifier", "Manufacturer", "Name", "Category", "ProductUrl", "Price", "ProductNumber", "Description", "ImageUrl", "DeliveryCost"]

def write(rows, excl, P):
    out = HERE
    with open(os.path.join(out, "compari_pepiniera.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, delimiter=";", quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    with open(os.path.join(out, "compari_pepiniera.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<Products>\n')
        for r in rows:
            f.write("  <Product>\n" + "".join(f"    <{k}>{escape(r[k])}</{k}>\n" for k in FIELDS if r[k]) + "  </Product>\n")
        f.write("</Products>\n")
    with open(os.path.join(out, "excluse.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["motiv", "titlu", "tip", "url", "pret"])
        for p, why in excl: w.writerow([why, p["title"], p["product_type"], f"{BASE}/products/{p['handle']}", p["variants"][0]["price"]])
    with open(os.path.join(out, "verificare_nume.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["titlu_site", "Name_feed", "Category"])
        for r in rows: w.writerow([r["_title"], r["Name"], r["Category"]])

if __name__ == "__main__":
    if "--fetch" in sys.argv: fetch()
    P, rows, excl = build()
    write(rows, excl, P)
    from collections import Counter
    print("publicate pe Online Store:", len(P))
    print("incluse:", len(rows), dict(Counter(r["Category"] for r in rows)))
    print("excluse:", len(excl), dict(Counter(w for _, w in excl)))
    ids = [r["Identifier"] for r in rows]; urls = [r["ProductUrl"] for r in rows]
    print("unice Identifier/URL:", len(set(ids)) == len(ids), len(set(urls)) == len(urls))
