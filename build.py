#!/usr/bin/env python3
"""Build index.html for agnesthedeveloper.github.io.

The copy (grouping, titles, one-liners, which charge events to show) lives in ACTORS
below. Prices and run counts come from the public Apify API at build time; the article
list comes from the public dev.to feed. Nothing here needs a token.

    python3 build.py          # fetches, writes index.html, prints a summary
    python3 build.py --dry    # fetches and prints the summary, writes nothing

Fails loudly if an actor on the Store is missing from ACTORS, so a new actor cannot be
left off the page by accident. An ACTORS entry that is no longer on the Store is skipped
with a warning.
"""
import html
import json
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone

USER = "agnes.developer.queen"
DEVTO = "agnes_the_dev_queen"
SITE = "https://agnesthedeveloper.github.io"
NAME = "Agnes Maina"
BIO = ("Independent developer. Web scrapers and data tools for B2B teams in the US, UK and EU: "
       "ad intelligence, people, companies, jobs. Pay per result.")
STORE = f"https://apify.com/{USER}"
GITHUB = "https://github.com/agnesthedeveloper"
X_URL = "https://x.com/agnesthedev"
X_HANDLE = "@agnesthedev"
DEVTO_URL = f"https://dev.to/{DEVTO}"
UTM = "utm_source=site&utm_medium=portfolio&utm_campaign=q4launch"

# (name on the Store, group, title, one line, [(charge event, label)], public code repo or None)
ACTORS = [
    ("linkedin-ad-library-scraper", "Ad intelligence", "LinkedIn Ad Library Scraper",
     "Every ad a company runs on LinkedIn: copy, creative, payer, run dates, impressions by "
     "country and targeting where LinkedIn publishes them.",
     [("ad", "ad")], f"{GITHUB}/linkedin-ad-library-scraper"),
    ("google-ads-transparency-scraper", "Ad intelligence", "Google Ads Transparency Scraper",
     "Every ad a brand runs on Google, by domain or advertiser name: text, image or video, "
     "first and last shown dates, countries.",
     [("ad", "ad")], f"{GITHUB}/google-ads-transparency-scraper"),
    ("meta-ad-library-scraper", "Ad intelligence", "Facebook Ad Library Scraper",
     "Every ad a brand runs on Facebook and Instagram: copy, image or video, start date, "
     "days running and EU reach.",
     [("ad", "ad")], None),
    ("linkedin-people-search-scraper", "People and companies", "LinkedIn People Search Scraper",
     "Public profiles by job title, company and location. Charged only when the person's own "
     "headline confirms the title and company.",
     [("matched-profile", "confirmed profile")], f"{GITHUB}/linkedin-people-search-scraper"),
    ("linkedin-profile-scraper", "People and companies", "LinkedIn Profile Scraper",
     "Profile URLs in; name, headline, location, current and past companies, education and "
     "followers out. Private profiles are free.",
     [("profile", "profile")], None),
    ("linkedin-company-scraper", "People and companies", "LinkedIn Company Scraper",
     "Company URL or name in; industry, size, headquarters, founded year, website, "
     "specialties and followers out.",
     [("company", "company")], f"{GITHUB}/linkedin-company-scraper"),
    ("linkedin-new-hires-finder", "People and companies", "LinkedIn New Hires Finder",
     "A company in; the decision makers who joined recently, with the month they started "
     "and the company they left.",
     [("new-hire", "new hire")], None),
    ("b2b-leads-finder", "People and companies", "B2B Leads Finder",
     "Public LinkedIn profiles by title, company and location, with email evidence where an "
     "address can be derived.",
     [("lead-with-verified-email", "lead with verified email"),
      ("lead-with-probable-email", "probable"), ("lead-without-email", "without email")], None),
    ("linkedin-jobs-scraper", "Jobs", "LinkedIn Jobs Scraper",
     "Full job descriptions, company, location and posted date, with a monitor mode that only "
     "delivers jobs you haven't seen.",
     [("job", "job")], f"{GITHUB}/linkedin-jobs-scraper"),
    ("indeed-jobs-scraper", "Jobs", "Indeed Jobs Scraper",
     "Salary ranges, company ratings and optional full descriptions, with the same monitor "
     "mode and a group-by-company view.",
     [("job", "job"), ("job-with-description", "with description")], None),
    ("google-hotels-scraper", "Other", "Google Hotels Scraper",
     "Prices for the dates and guests you choose: nightly and total price, rating, reviews, "
     "star class, coordinates and website for every hotel on the results page.",
     [("hotel", "hotel"), ("hotel-offers", "with offers")], None),
    ("bilibili-scraper", "Other", "Bilibili Scraper",
     "Video search, details, popular, danmaku, comments, subtitle transcripts and profiles.",
     [("video", "video"), ("comment", "comment")], None),
]
GROUPS = ["Ad intelligence", "People and companies", "Jobs", "Other"]

esc = html.escape


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "agnesthedeveloper.github.io build.py"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def usd(x):
    s = f"{x:.5f}".rstrip("0")
    frac = s.split(".")[1]
    if len(frac) < 2:
        s += "0" * (2 - len(frac))
    return "$" + s


def current_pricing(actor):
    """The pricing entry in force now (entries are chronological; skip future-dated ones)."""
    now = datetime.now(timezone.utc)
    live = {}
    for p in actor.get("pricingInfos") or []:
        started = p.get("startedAt")
        if started and datetime.fromisoformat(started.replace("Z", "+00:00")) > now:
            continue
        live = p
    return live


def event_prices(actor):
    ev = (current_pricing(actor).get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
    return {k: v.get("eventPriceUsd") for k, v in ev.items()}


def join_names(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def start_note(start_fees):
    fees = Counter(v for v in start_fees.values() if v is not None)
    if not fees:
        return ""
    common = fees.most_common(1)[0][0]
    bits = [f"Each run also carries a start fee: {usd(common)} on most actors"]
    for fee, _ in fees.most_common():
        if fee != common:
            bits.append(f"{usd(fee)} on {join_names(t for t, v in start_fees.items() if v == fee)}")
    s = ", ".join(bits)
    none = [t for t, v in start_fees.items() if v is None]
    if none:
        s += f"; {join_names(none)} {'has' if len(none) == 1 else 'have'} none"
    return s + "."


def fmt_date(iso):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d.day} {d.strftime('%b %Y')}"


def actor_rows(rows):
    out = []
    for g in GROUPS:
        if not rows[g]:
            continue
        out.append(f"<h3>{esc(g)}</h3>\n<table>")
        for name, title, line, price, code in rows[g]:
            url = f"{STORE}/{name}?{UTM}"
            code_html = f' <a class="code" href="{esc(code)}">code</a>' if code else ""
            out.append(f'<tr><td><a href="{esc(url)}"><strong>{esc(title)}</strong></a><br>'
                       f'<span class="muted">{esc(line)}</span>{code_html}</td>'
                       f'<td class="price">{esc(price)}</td></tr>')
        out.append("</table>")
    return "\n".join(out)


def article_items(articles):
    out = []
    for a in sorted(articles, key=lambda a: a["published_at"], reverse=True):
        out.append(f'<li><a href="{esc(a["url"])}">{esc(a["title"])}</a>'
                   f'<span class="date">{esc(fmt_date(a["published_at"]))}</span></li>')
    return "\n".join(out)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agnes Maina: pay-per-result web scrapers on Apify</title>
<meta name="description" content="@@BIO@@">
<link rel="canonical" href="@@SITE@@/">
<link rel="icon" href="avatar.png">
<link rel="me" href="@@GITHUB@@">
<link rel="me" href="@@X_URL@@">
<meta property="og:type" content="website">
<meta property="og:title" content="Agnes Maina: pay-per-result web scrapers on Apify">
<meta property="og:description" content="@@BIO@@">
<meta property="og:url" content="@@SITE@@/">
<meta property="og:image" content="@@SITE@@/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@@X_HANDLE@@">
<script type="application/ld+json">@@JSONLD@@</script>
<style>
:root{--ink:#1a1a1a;--muted:#5f6368;--line:#e6e6e6;--accent:#0b5fff}
body{margin:0;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff}
main{max-width:800px;margin:0 auto;padding:40px 20px 60px}
header{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
header img{width:88px;height:88px;border-radius:50%}
h1{font-size:28px;margin:0}
.bio{margin:4px 0 6px;color:var(--muted)}
.links a{margin-right:14px}
.lede{margin:28px 0 0;font-size:17px}
h2{font-size:20px;margin:40px 0 8px}
h3{font-size:13px;margin:22px 0 4px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:15px}
td{padding:9px 8px 9px 0;border-top:1px solid var(--line);vertical-align:top}
td.price{white-space:nowrap;text-align:right;color:var(--muted);padding-right:0}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
a.code{font-size:13px;margin-left:6px}
.muted{color:var(--muted)}.small{font-size:14px}
code{font-size:14px;background:#f3f4f6;padding:1px 5px;border-radius:4px}
ul.articles{padding:0;list-style:none;margin:0}
ul.articles li{padding:8px 0;border-top:1px solid var(--line)}
.date{color:var(--muted);font-size:13px;margin-left:8px;white-space:nowrap}
footer{margin-top:50px;font-size:13px;color:var(--muted)}
@media(max-width:600px){td.price{white-space:normal}}
</style>
</head>
<body>
<main>
<header>
  <img src="avatar.png" alt="" width="88" height="88">
  <div>
    <h1>@@NAME@@</h1>
    <p class="bio">@@BIO@@</p>
    <p class="links"><a href="@@STORE@@?@@UTM@@">Apify Store</a> <a href="@@GITHUB@@">GitHub</a> <a href="@@DEVTO_URL@@">Dev.to</a> <a href="@@X_URL@@">@@X_HANDLE@@</a></p>
  </div>
</header>

<p class="lede"><strong>@@N@@ actors</strong> on the Apify Store, <strong id="runs">@@RUNS@@</strong> runs so far. No LinkedIn login, no cookies, no account of yours at risk. You pay per row that clears each actor's check; rows that don't are delivered with <code>charged: false</code> at $0.</p>

<h2>Actors</h2>
@@ACTORS@@
<p class="muted small">@@STARTNOTE@@ Every Apify account gets $5 of free platform credit each month, enough to try any of them.</p>

<h2>How pricing works</h2>
<ul>
<li>You pay per result, not per compute minute. The price in the table is the whole story, plus the per-run start fee.</li>
<li>Every row carries a <code>charged</code> flag. Rows that don't clear the actor's check (wrong company, incomplete job, duplicate) are still delivered so you can see them, at $0.</li>
<li>Every actor reads public pages only. There is no login to hand over, so no account of yours is at risk.</li>
</ul>

<h2>Writing</h2>
<p class="muted">Measured runs, what each source actually publishes, and where the data stops.</p>
<ul class="articles">
@@ARTICLES@@
</ul>

<h2>Contact</h2>
<p>A bug or a missing field: the Issues tab on the actor's Apify page, that's where I track and answer them. Anything else: <a href="@@X_URL@@">@@X_HANDLE@@</a> on X or <a href="@@GITHUB@@">GitHub</a>.</p>

<footer>Updated @@DATE@@. Prices and counts are read from the Apify Store when this page is built.</footer>
</main>
<script>
fetch("https://api.apify.com/v2/store?username=@@USER@@&limit=100")
  .then(function(r){return r.json()})
  .then(function(d){var n=0;(d.data.items||[]).forEach(function(i){n+=(i.stats&&i.stats.totalRuns)||0});
    if(n>0){document.getElementById("runs").textContent=n.toLocaleString("en-US")}})
  .catch(function(){});
</script>
</body>
</html>
"""


def main():
    dry = "--dry" in sys.argv
    items = get(f"https://api.apify.com/v2/store?username={USER}&limit=100")["data"]["items"]
    on_store = {i["name"]: i for i in items}
    new = sorted(set(on_store) - {a[0] for a in ACTORS})
    if new:
        sys.exit(f"on the Store but not in ACTORS (add copy, then rebuild): {', '.join(new)}")
    warnings = []
    rows = {g: [] for g in GROUPS}
    start_fees = {}
    for name, group, title, line, events, code in ACTORS:
        if name not in on_store:
            warnings.append(f"{name}: not on the Store any more, skipped")
            continue
        prices = event_prices(get(f"https://api.apify.com/v2/acts/{USER}~{name}")["data"])
        parts = []
        for i, (key, label) in enumerate(events):
            if key not in prices:
                sys.exit(f"{name}: charge event {key!r} not in {sorted(prices)}")
            parts.append(f"{usd(prices[key])} / {label}" if i == 0 else f"{usd(prices[key])} {label}")
        start = [v for k, v in prices.items() if "start" in k]
        start_fees[title] = start[0] if start else None
        rows[group].append((name, title, line, ", ".join(parts), code))
    runs = sum((i.get("stats") or {}).get("totalRuns") or 0 for i in items)
    n = sum(len(v) for v in rows.values())
    articles = get(f"https://dev.to/api/articles?username={DEVTO}&per_page=100")

    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Person", "name": NAME, "url": SITE + "/",
        "jobTitle": "Independent developer", "description": BIO,
        "sameAs": [STORE, GITHUB, DEVTO_URL, X_URL],
    })
    today = date.today()
    page = TEMPLATE
    for key, val in {
        "BIO": esc(BIO), "SITE": SITE, "GITHUB": GITHUB, "X_URL": X_URL, "X_HANDLE": X_HANDLE,
        "NAME": esc(NAME), "STORE": STORE, "UTM": UTM, "DEVTO_URL": DEVTO_URL, "USER": USER,
        "JSONLD": jsonld, "N": str(n), "RUNS": f"{runs:,}", "ACTORS": actor_rows(rows),
        "STARTNOTE": esc(start_note(start_fees)), "ARTICLES": article_items(articles),
        "DATE": f"{today.day} {today.strftime('%B %Y')}",
    }.items():
        page = page.replace(f"@@{key}@@", val)
    if "@@" in page:
        sys.exit("unfilled placeholder in the template")

    for w in warnings:
        print("warning:", w)
    print(f"{n} actors, {runs:,} runs, {len(articles)} articles, {len(page):,} bytes")
    if dry:
        return
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote index.html")


if __name__ == "__main__":
    main()
