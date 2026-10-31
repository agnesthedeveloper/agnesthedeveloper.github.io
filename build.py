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
     "headline confirms the requested match.",
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
     "A company in; the decision makers who started a role recently, with the month they started "
     "and their previous company.",
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
        group_id = "group-" + g.lower().replace(" ", "-")
        out.append(f'<section class="actor-group" aria-labelledby="{group_id}">'
                   f'<h3 id="{group_id}">{esc(g)}</h3>\n'
                   f'<table class="actor-table" aria-labelledby="{group_id}"><tbody>')
        for name, title, line, parts, code in rows[g]:
            url = f"{STORE}/{name}?{UTM}"
            code_html = f' <a class="code" href="{esc(code)}">code</a>' if code else ""
            price_html = "<br>".join(esc(p) for p in parts)  # one tier per line, keeps the column narrow
            out.append(f'<tr><th scope="row"><a class="actor-title" href="{esc(url)}">{esc(title)}</a>'
                       f'<p class="actor-description">{esc(line)}</p>{code_html}</th>'
                       f'<td class="price">{price_html}</td></tr>')
        out.append("</tbody></table></section>")
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
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="628">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@@X_HANDLE@@">
<meta name="twitter:title" content="Agnes Maina: pay-per-result web scrapers on Apify">
<meta name="twitter:description" content="@@BIO@@">
<meta name="twitter:image" content="@@SITE@@/og.png">
<script type="application/ld+json">@@JSONLD@@</script>
<link rel="stylesheet" href="style.css">
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="#main"><img src="avatar.png" alt="Agnes Maina brand mark" width="36" height="36"><span>@@NAME@@</span></a>
    <nav aria-label="Main navigation">
      <div class="section-links"><a href="#actors">Actors</a><a href="#pricing">Pricing</a><a href="#writing">Writing</a><a href="#contact">Contact</a></div>
      <a class="store-link" href="@@STORE@@?@@UTM@@">Apify Store <span aria-hidden="true">↗</span></a>
    </nav>
  </div>
</header>

<main id="main">
<div class="hero-area">
  <section class="hero" aria-labelledby="hero-title">
    <h1 id="hero-title">Public-data scrapers,<br><span>priced per result.</span></h1>
    <p class="hero-subhead"><span>@@N@@ pay-per-result scrapers on the Apify Store: ad libraries, LinkedIn people and companies, jobs.</span> <span>No LinkedIn login or cookies; no account of yours at risk.</span></p>
    <div class="hero-actions">
      <a class="button button-primary" href="@@STORE@@?@@UTM@@">Browse the actors <span aria-hidden="true">↗</span></a>
      <a class="button button-secondary" href="#pricing">How pricing works</a>
    </div>
    <p class="run-count"><span class="status-dot" aria-hidden="true"></span><strong>@@N@@ actors</strong> on the Apify Store <span class="separator" aria-hidden="true">·</span> <span><strong id="runs">@@RUNS@@</strong> runs so far.</span></p>
  </section>

  <figure class="dataset-card">
    <div class="window-bar">
      <svg class="window-dots" width="42" height="10" viewBox="0 0 42 10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="#d1d5db"/><circle cx="21" cy="5" r="4" fill="#d1d5db"/><circle cx="37" cy="5" r="4" fill="#d1d5db"/></svg>
      <p id="dataset-title">LinkedIn People Search Scraper <span aria-hidden="true">·</span> run output</p>
    </div>
    <div class="dataset-heading"><span>Public profiles</span><span class="dataset-label">Pay per confirmed match</span></div>
    <div class="dataset-scroll" role="region" aria-labelledby="dataset-title" tabindex="0">
      <!-- Real test-run headlines from docs-people-search.md. Missing matched values stay blank. -->
      <table class="dataset-table">
        <caption class="sr-only">Documented sample rows. A dash means no matched value was provided in the sample.</caption>
        <thead><tr><th scope="col">Headline</th><th scope="col">Matched title</th><th scope="col">Company</th><th scope="col">Charged</th></tr></thead>
        <tbody>
          <tr><td>Chief Financial Officer, Asana</td><td>CFO</td><td>Asana</td><td><span class="pill charged">charged: true</span></td></tr>
          <tr><td>Chief Financial Officer at Linear Controls</td><td class="empty">—</td><td class="empty">—</td><td><span class="pill not-charged">charged: false</span></td></tr>
          <tr><td>Executive Business Partner to CTO @ Vercel</td><td class="empty">—</td><td class="empty">—</td><td><span class="pill not-charged">charged: false</span></td></tr>
          <tr><td>Head of Stock Administration at Asana</td><td class="empty">—</td><td class="empty">—</td><td><span class="pill not-charged">charged: false</span></td></tr>
        </tbody>
      </table>
    </div>
    <figcaption>Real headlines from the actor README. <span>— = no matched value in the sample.</span><span class="scroll-hint">Scroll to see all columns →</span></figcaption>
  </figure>
  <p class="dataset-note">For People Search, you pay per confirmed match; other rows arrive with <code>charged: false</code> at $0.</p>
</div>

<div class="content">
<section id="actors" class="actors section" aria-labelledby="actors-title">
  <div class="section-heading"><h2 id="actors-title">Actors</h2><span class="section-label">Public data. Pay per result.</span></div>
  @@ACTORS@@
  <p class="pricing-note">@@STARTNOTE@@ Every Apify account gets $5 of free platform credit each month, enough to try any of them.</p>
</section>

<section id="pricing" class="section pricing" aria-labelledby="pricing-title">
<h2 id="pricing-title">How pricing works</h2>
<ul class="pricing-list">
<li>You pay per result, not per compute minute, plus the start fee where applicable. See each actor's Store page for all price tiers.</li>
<li>People Search rows carry a <code>charged</code> flag. Unconfirmed matches are still delivered, at $0.</li>
<li>The LinkedIn actors need no login or cookies, so no LinkedIn account of yours is at risk.</li>
</ul>
</section>

<section id="writing" class="section writing" aria-labelledby="writing-title">
<div class="section-heading"><h2 id="writing-title">Writing</h2><a class="section-label" href="@@DEVTO_URL@@">Dev.to <span aria-hidden="true">↗</span></a></div>
<p class="muted">Measured runs, what each source actually publishes, and where the data stops.</p>
<ul class="articles">
@@ARTICLES@@
</ul>
</section>

<section id="contact" class="section contact" aria-labelledby="contact-title">
<h2 id="contact-title">Contact</h2>
<p>A bug or a missing field: the Issues tab on the actor's Apify page, that's where I track and answer them. Anything else: <a href="@@X_URL@@">@@X_HANDLE@@</a> on X or <a href="@@GITHUB@@">GitHub</a>.</p>
<div class="about">
  <p class="bio">@@BIO@@</p>
  <p class="links"><a href="@@STORE@@?@@UTM@@">Apify Store</a><a href="@@GITHUB@@">GitHub</a><a href="@@DEVTO_URL@@">Dev.to</a><a href="@@X_URL@@">@@X_HANDLE@@</a></p>
</div>
</section>
</div>
</main>
<footer class="footer"><p>Updated @@DATE@@. Prices and counts are read from the Apify Store when this page is built.</p></footer>
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
        rows[group].append((name, title, line, parts, code))
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
