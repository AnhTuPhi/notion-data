import os
import json
import time
import feedparser
import cloudscraper

from curl_cffi import requests as cf_requests
from notion_client import Client
from datetime import datetime
from email.utils import parsedate_to_datetime


RSS_URLS = [
    "https://blackswain.substack.com/feed",
    "https://bachhoavienvong.substack.com/feed",
    "https://zoedatalens.substack.com/feed",
    "https://vohoanghac.com/feed",
    "https://cyclegatekeeper.substack.com/feed",
    "https://awriterofeverything.substack.com/feed",
    "https://grow.tomorrowmarketers.org/feed",
    "https://anhmle.substack.com/feed",
    "https://sdcourse.substack.com/feed",
    "https://architecturenotes.co/feed",
    "https://substack.changngocgia.com/feed",
    "https://dantech.substack.com/feed",
    "https://cuonganhecowriter.substack.com/feed",
    "https://taichinhnguocdoi.substack.com/feed",
    "https://www.uptrend.vn/feed",
    "https://laiho999.substack.com/feed",
    "https://hieungoc.substack.com/feed",
    "https://kimthanhstock.substack.com/feed",
    "https://newsletter.grokking.org/feed",
    "https://hienle323298.substack.com/feed",
    "https://trongharvey.substack.com/feed",
    "https://hoikydautu.substack.com/feed",
    "https://nanginvests.substack.com/feed",
    "https://vyvo.substack.com/feed",
    "https://mrpcfun.substack.com/feed",
    "https://vutr.substack.com/feed",
    "https://vutuyen.substack.com/feed",
    "https://vnwyckoffclub.substack.com/feed",
    "https://vnhacker.substack.com/feed",
]


DATABASE_ID = os.environ["DATABASE_ID"]

notion = Client(auth=os.environ["NOTION_TOKEN"])


def get_data_source_id():
    db = notion.databases.retrieve(database_id=DATABASE_ID)
    sources = db.get("data_sources") or []
    if not sources:
        raise RuntimeError(
            f"Database {DATABASE_ID} has no data_sources. "
            "Make sure the integration has access and the API version supports data sources."
        )
    return sources[0]["id"]


DATA_SOURCE_ID = get_data_source_id()


BROWSER_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36",
    "Accept":
        "application/rss+xml, application/xml;q=0.9, "
        "text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def try_curl_cffi(url):
    try:
        r = cf_requests.get(
            url,
            headers=BROWSER_HEADERS,
            impersonate="chrome124",
            timeout=30,
        )
        if r.status_code == 200:
            return r.content
        print(f"  curl_cffi HTTP {r.status_code}")
    except Exception as e:
        print(f"  curl_cffi error: {e}")
    return None


def try_cloudscraper(url):
    try:
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, headers=BROWSER_HEADERS, timeout=30)
        if r.status_code == 200:
            return r.content
        print(f"  cloudscraper HTTP {r.status_code}")
    except Exception as e:
        print(f"  cloudscraper error: {e}")
    return None


def normalize_feedparser(feed):
    posts = []
    for e in feed.entries:
        link = e.get("link", "")
        if not link:
            continue
        posts.append({
            "title": e.get("title", "(untitled)"),
            "link": link,
            "published": e.get("published", ""),
        })
    return posts


def normalize_substack_api(content):
    data = json.loads(content)
    posts = []
    for p in data:
        link = p.get("canonical_url") or p.get("url", "")
        if not link:
            continue
        posts.append({
            "title": p.get("title", "(untitled)"),
            "link": link,
            "published": p.get("post_date") or "",
        })
    return posts


def fetch_posts(url):
    # Tier 1+2: full browser headers + curl_cffi (Chrome TLS impersonation)
    content = try_curl_cffi(url)
    if content:
        feed = feedparser.parse(content)
        if feed.entries:
            return normalize_feedparser(feed)
        print("  curl_cffi: empty feed")

    # Tier 3: cloudscraper (handles older CF JS challenge)
    content = try_cloudscraper(url)
    if content:
        feed = feedparser.parse(content)
        if feed.entries:
            return normalize_feedparser(feed)
        print("  cloudscraper: empty feed")

    # Fallback: Substack archive JSON API (only for *.substack.com)
    if ".substack.com" in url:
        base = url.rsplit("/feed", 1)[0]
        api = f"{base}/api/v1/archive?sort=new&limit=20"
        print(f"  fallback API: {api}")
        content = try_curl_cffi(api)
        if content:
            try:
                return normalize_substack_api(content)
            except Exception as e:
                print(f"  api parse error: {e}")

    return None


def convert_date(published):
    if not published:
        return datetime.utcnow().isoformat()
    try:
        return parsedate_to_datetime(published).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(
            published.replace("Z", "+00:00")
        ).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


def create_post(post):
    print("Creating:", post["title"])
    notion.pages.create(
        parent={"data_source_id": DATA_SOURCE_ID},
        properties={
            "Title": {
                "title": [
                    {"text": {"content": post["title"]}}
                ]
            },
            "URL": {"url": post["link"]},
            "Published": {
                "date": {"start": convert_date(post["published"])}
            },
        },
    )


def purge_database():
    print("Archiving existing pages in Notion DB...")
    count = 0
    cursor = None
    while True:
        kwargs = {"data_source_id": DATA_SOURCE_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.data_sources.query(**kwargs)
        for page in resp["results"]:
            try:
                notion.pages.update(page_id=page["id"], archived=True)
                count += 1
            except Exception as e:
                print(f"  archive error on {page['id']}: {e}")
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    print(f"Archived {count} pages")


purge_database()


seen_links = set()

for rss_url in RSS_URLS:

    print("====================")
    print("Fetching:", rss_url)

    posts = fetch_posts(rss_url)

    if posts is None:
        print("Skip (all tiers failed):", rss_url)
        continue

    print("Found:", len(posts))

    for post in posts:

        if post["link"] in seen_links:
            print("Dup skip:", post["title"])
            continue

        try:
            create_post(post)
            seen_links.add(post["link"])
        except Exception as e:
            print("ERROR:", e)

    time.sleep(1)


print("Sync completed:", len(seen_links), "posts")
