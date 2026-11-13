"""
AeroIntel — feed collector.
Runs in GitHub Actions every 30 minutes. Reads sources.json, fetches every RSS/Atom
feed server-side, and writes feeds.json (articles + per-source health) for the web app.
No third-party dependencies: Python standard library only.
"""
import json, re, html, sys, time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_ITEMS = 12          # per source
MAX_AGE_DAYS = 30       # older items are dropped; a source with nothing newer is "stale"
TIMEOUT = 20
UA = "Mozilla/5.0 (compatible; AeroIntelBot/4.0; +https://github.com/)"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

def first_img(s):
    m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", s or "", re.I)
    return m.group(1) if m else None

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def text(el, path):
    x = el.find(path, NS)
    return (x.text or "").strip() if x is not None and x.text else ""

def is_http(u):
    return isinstance(u, str) and u.lower().startswith(("http://", "https://"))

def _repair(raw):
    """Fix the most common XML errors in real-world feeds (stray '&', control characters)."""
    s = raw.decode("utf-8", errors="replace")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = re.sub(r"&(?!(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)", "&amp;", s)
    return s.encode("utf-8")

def parse_feed(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(_repair(raw))
    items = []
    tag = root.tag.lower()
    if tag.endswith("feed"):  # Atom
        for e in root.findall("atom:entry", NS):
            link = ""
            for l in e.findall("atom:link", NS):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", ""); break
            body = text(e, "atom:summary") or text(e, "atom:content")
            items.append(dict(title=text(e, "atom:title"), link=link,
                              date=parse_date(text(e, "atom:published") or text(e, "atom:updated")),
                              desc=body, img=first_img(body)))
    else:  # RSS 2.0 / RDF
        for e in root.iter():
            if not e.tag.lower().endswith("item"):
                continue
            body = text(e, "content:encoded") or text(e, "description")
            img = None
            for p in ("media:content", "media:thumbnail"):
                m = e.find(p, NS)
                if m is not None and m.get("url"):
                    img = m.get("url"); break
            enc = e.find("enclosure")
            if not img and enc is not None and (enc.get("type") or "").startswith("image"):
                img = enc.get("url")
            items.append(dict(title=text(e, "title"), link=text(e, "link"),
                              date=parse_date(text(e, "pubDate") or text(e, "dc:date")),
                              desc=body, img=img or first_img(body)))
    return items

def fetch(src):
    t0 = time.time()
    out = dict(id=src["id"], status="error", count=0, latest=None, error=None)
    try:
        req = urllib.request.Request(src["feed"], headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
        items = parse_feed(raw)
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {str(ex)[:120]}"
        return out, []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    clean = []
    for it in items:
        title = strip_html(it["title"])[:160]
        link = (it["link"] or "").strip()
        if not title or not is_http(link):
            continue
        d = it["date"] or now
        if d > now + timedelta(hours=1):
            d = now
        clean.append(dict(title=title, link=link, date=d,
                          desc=strip_html(it["desc"])[:220],
                          img=it["img"] if is_http(it["img"]) else None))
    clean.sort(key=lambda x: x["date"], reverse=True)
    if clean:
        out["latest"] = clean[0]["date"].strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = [c for c in clean if c["date"] >= cutoff][:MAX_ITEMS]
    if not clean:
        out["status"] = "empty"
    elif not fresh:
        out["status"] = "stale"
    else:
        out["status"] = "ok"
    out["count"] = len(fresh)
    arts = [dict(title=c["title"], link=c["link"], date=c["date"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                 desc=c["desc"], img=c["img"], source=src["id"]) for c in fresh]
    out["ms"] = int((time.time() - t0) * 1000)
    return out, arts

# ---------- trending terms ----------
STOP = set("""a an and or of to in on for with at by from as is are be been was were it its into over after before amid about
against than that this these those their his her our your new how why what who when where which will can could may might would should
says said say gets get set just now still back up out off not but no yes more most less first last next top big two three one four five
us u.s uk eu air force forces army navy marine marines corps space defense defence military aircraft jet jets fighter fighters drone drones
war wars news report reports video photos watch update week weeks day days year years plan plans deal deals contract contracts program
programs programme programmes system systems new world global national international government minister ministry chief head
sample headline headlines live title appears here story stories exclusive analysis opinion commentary podcast interview
january february march april may june july august september october november december monday tuesday wednesday thursday friday saturday sunday
mr ms dr general gen lt col secretary president prime""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-/][A-Za-z0-9]+)*|\d+[A-Za-z][A-Za-z0-9-]*")

def _is_term(w):
    lw = w.lower()
    if lw in STOP or len(w) < 3 and not re.search(r"\d", w):
        return False
    if re.search(r"[A-Za-z]", w) and re.search(r"\d", w):      # F-35, A400M, J-20, KC-46
        return True
    if w.isupper() and 2 <= len(w) <= 6:                            # NATO, GCAP, CCA
        return True
    return w[0].isupper() and len(w) >= 4

def candidates(title):
    words = [re.sub(r"(?<=\d)s$", "", w) for w in WORD.findall(title)]   # F-35s -> F-35
    out = set()
    for i, w in enumerate(words):
        if _is_term(w):
            out.add(w)
        if i + 1 < len(words):
            w2 = words[i + 1]
            ok1 = len(w) > 2 or re.search(r"\d", w)
            ok2 = len(w2) > 2 or re.search(r"\d", w2)
            if w[0].isupper() and w2[0].isupper() and w.lower() not in STOP and w2.lower() not in STOP and ok1 and ok2:
                out.add(w + " " + w2)
    return out

def trending(articles, now, top=5):
    """Terms that appear in many headlines this week but were rare in the 3 weeks before."""
    week = now - timedelta(days=7)
    recent, older, srcs, casing = {}, {}, {}, {}
    for a in articles:
        d = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
        for term in candidates(a["title"]):
            k = term.lower()
            casing.setdefault(k, {}); casing[k][term] = casing[k].get(term, 0) + 1
            if d >= week:
                recent[k] = recent.get(k, 0) + 1
                srcs.setdefault(k, set()).add(a["source"])
            else:
                older[k] = older.get(k, 0) + 1
    scored = []
    for k, n in recent.items():
        base = older.get(k, 0) * 7 / 23
        if n >= 3 and len(srcs[k]) >= 2 and n >= 2 * base + 1:
            scored.append((n - base + (0.5 if " " in k else 0), n, k))   # prefer "Rafale F5" over "Rafale"
    scored.sort(reverse=True)
    picked = []
    for _, n, k in scored:
        if any(k in p["key"] or p["key"] in k for p in picked):   # skip "rafale" if "rafale f5" already in
            continue
        term = max(casing[k].items(), key=lambda x: x[1])[0]
        picked.append(dict(key=k, term=term, n=n, sources=len(srcs[k])))
        if len(picked) == top:
            break
    return [dict(term=p["term"], n=p["n"], sources=p["sources"]) for p in picked]

def norm(u):
    return re.sub(r"[?#].*$", "", u.lower()).rstrip("/")

def main():
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch, sources))
    health, articles, seen_link, seen_title = [], [], set(), set()
    for (h, arts) in results:
        health.append(h)
        for a in arts:
            k1, k2 = norm(a["link"]), a["title"].lower()
            if k1 in seen_link or k2 in seen_title:
                continue
            seen_link.add(k1); seen_title.add(k2)
            articles.append(a)
    articles.sort(key=lambda a: a["date"], reverse=True)
    now = datetime.now(timezone.utc)
    data = dict(generated=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                sources=sources, health=health, trending=trending(articles, now), items=articles)
    (ROOT / "feeds.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for h in health if h["status"] == "ok")
    print(f"{ok}/{len(health)} sources OK, {len(articles)} articles, trending: {[x['term'] for x in data['trending']]}")
    for h in health:
        print(f"  {h['status']:6} {h['id']:16} {h['count']:3}  {h.get('error') or ''}")

if __name__ == "__main__":
    main()
