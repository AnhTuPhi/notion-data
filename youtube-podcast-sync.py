import os
import re
import time
import feedparser
import cloudscraper

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup
from notion_client import Client


# ==========================================================================
# CONFIG — edit these lists to add/remove channels & podcasts
# ==========================================================================
#
# YouTube channel_id lookup:
#   1. Mở channel page, view-source, tìm "channelId" hoặc "externalId"
#   2. Hoặc paste channel URL vào https://commentpicker.com/youtube-channel-id.php
#   3. channel_id luôn bắt đầu bằng "UC" và dài 24 ký tự
# ==========================================================================

YOUTUBE_CHANNELS = [
    # Format: (channel_id, category, display_name)

    # === Tech Stack ===
    # ("UCsBjURrPoezykLs9EqgamOA", "Tech", "Fireship"),
    ("UChG2EWuXoW7Tgof35WjbsnQ", "E-SPORT", "LoL Esports VN"),
    
    # ("UCUyeluBRhGPCW4rPe_UvBZQ", "Tech", "ThePrimeagen"),
    # ("UCbRP3c757lWg9M-U7TyEkXA", "Tech", "Theo - t3.gg"),
    # ("UC8butISFwT-Wl7EV0hUK0BQ", "Tech", "freeCodeCamp"),

    # === Crypto ===
    # ("UCqK_GSMbpiV8spgD3ZGloSw", "Crypto", "Coin Bureau"),
    # ("UCRvqjQPSeaWn-uEx-w0XOIg", "Crypto", "Benjamin Cowen"),

    # === Stock / Finance ===
    # ("UCFCEuCsyWP0YkP3CgCeAvJg", "Finance", "The Plain Bagel"),
    # ("UCASM0XgfutHsdMnv9NoTGOg", "Finance", "Patrick Boyle"),

    # Add yours here, e.g.:
    # ("UC___xxx___", "Tech", "Channel Name"),
]

PODCAST_FEEDS = [
    # Format: (feed_url, category, display_name)

    # ("https://feeds.simplecast.com/54nAGcIl", "Tech", "Syntax.fm"),
    # ("https://lexfridman.com/feed/podcast/", "Tech", "Lex Fridman"),
    # ("https://feeds.megaphone.fm/changelog", "Tech", "The Changelog"),

    # Add yours here
]


# ==========================================================================
# SETUP
# ==========================================================================

VN_TZ = timezone(timedelta(hours=7))

DATABASE_ID = os.environ["DATABASE_ID"]
notion = Client(auth=os.environ["NOTION_TOKEN"])


def get_data_source_id():
    db = notion.databases.retrieve(database_id=DATABASE_ID)
    sources = db.get("data_sources") or []
    if not sources:
        raise RuntimeError(
            f"Database {DATABASE_ID} has no data_sources. "
            "Make sure integration has access."
        )
    return sources[0]["id"]


DATA_SOURCE_ID = get_data_source_id()


WARP_PROXY = os.environ.get("WARP_PROXY", "").strip() or None


def _proxies():
    if WARP_PROXY:
        return {"http": WARP_PROXY, "https": WARP_PROXY}
    return None


if WARP_PROXY:
    print(f"Using WARP proxy: {WARP_PROXY}")
else:
    print("No WARP_PROXY set; direct connection")


BROWSER_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36",
    "Accept":
        "application/atom+xml, application/rss+xml, "
        "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
}


# ==========================================================================
# HTTP fetch (same tier chain as substack-sync)
# ==========================================================================

def _peek(content):
    try:
        return content.decode("utf-8", errors="replace")[:200].replace("\n", " ")
    except Exception:
        return ""


def try_curl_cffi(url):
    try:
        r = cf_requests.get(
            url,
            headers=BROWSER_HEADERS,
            impersonate="chrome124",
            timeout=30,
            proxies=_proxies(),
        )
        if r.status_code == 200:
            return r.content
        print(f"  curl_cffi HTTP {r.status_code} | {_peek(r.content)}")
    except Exception as e:
        print(f"  curl_cffi error: {e}")
    return None


def try_cloudscraper(url):
    try:
        scraper = cloudscraper.create_scraper()
        r = scraper.get(url, headers=BROWSER_HEADERS, timeout=30, proxies=_proxies())
        if r.status_code == 200:
            return r.content
        print(f"  cloudscraper HTTP {r.status_code} | {_peek(r.content)}")
    except Exception as e:
        print(f"  cloudscraper error: {e}")
    return None


def fetch_feed_bytes(url):
    return try_curl_cffi(url) or try_cloudscraper(url)


# ==========================================================================
# Date utils — filter to "today in Vietnam timezone"
# ==========================================================================

def today_start_vn():
    now = datetime.now(VN_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_pub_date(raw):
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def is_today_vn(raw_pub):
    dt = parse_pub_date(raw_pub)
    if not dt:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ) >= today_start_vn()


def convert_date(raw):
    dt = parse_pub_date(raw)
    if not dt:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ==========================================================================
# Feed normalizers
# ==========================================================================

def yt_channel_feed_url(channel_id):
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def yt_thumbnail(video_id):
    # hqdefault.jpg always exists for every video (480x360)
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def extract_youtube_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def normalize_youtube_entries(feed, channel_name, category):
    posts = []
    for e in feed.entries:
        link = e.get("link", "")
        if not link:
            continue

        published_raw = e.get("published", "")
        if not is_today_vn(published_raw):
            continue

        video_id = e.get("yt_videoid") or extract_youtube_video_id(link)
        description = e.get("media_description") or e.get("summary", "")
        thumb = yt_thumbnail(video_id) if video_id else None

        posts.append({
            "title": e.get("title", "(untitled)"),
            "link": link,
            "published": published_raw,
            "channel": channel_name,
            "category": category,
            "type": "YouTube",
            "thumbnail": thumb,
            "description": description,
            "media_url": link,
        })
    return posts


def normalize_podcast_entries(feed, podcast_name, category):
    posts = []
    for e in feed.entries:
        link = e.get("link", "")
        if not link:
            continue

        published_raw = e.get("published", "")
        if not is_today_vn(published_raw):
            continue

        audio_url = None
        for enc in (e.get("enclosures") or []):
            if (enc.get("type") or "").startswith("audio"):
                audio_url = enc.get("href")
                break

        description = e.get("summary", "")
        contents = getattr(e, "content", None)
        if contents:
            description = contents[0].value

        thumb = None
        if isinstance(e.get("image"), dict):
            thumb = e.image.get("href")
        if not thumb:
            mt = e.get("media_thumbnail")
            if mt and isinstance(mt, list):
                thumb = mt[0].get("url")
        if not thumb:
            feed_img = getattr(feed.feed, "image", None)
            if feed_img:
                thumb = getattr(feed_img, "href", None) or (
                    feed_img.get("href") if isinstance(feed_img, dict) else None
                )

        posts.append({
            "title": e.get("title", "(untitled)"),
            "link": link,
            "published": published_raw,
            "channel": podcast_name,
            "category": category,
            "type": "Podcast",
            "thumbnail": thumb,
            "description": description,
            "media_url": audio_url or link,
        })
    return posts


# ==========================================================================
# Notion blocks
# ==========================================================================

def _text(content):
    return {"type": "text", "text": {"content": content[:2000]}}


def _paragraph(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [_text(text)]},
    }


def description_to_blocks(description_html, max_chars=3000):
    if not description_html:
        return []
    try:
        soup = BeautifulSoup(description_html, "html.parser")
    except Exception:
        return []
    text = soup.get_text(separator="\n", strip=True)
    if not text:
        return []
    if len(text) > max_chars:
        text = text[:max_chars] + "…"

    blocks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        for i in range(0, len(para), 2000):
            blocks.append(_paragraph(para[i:i + 2000]))
    return blocks


def build_blocks(post):
    blocks = []

    if post["type"] == "YouTube":
        blocks.append({
            "object": "block",
            "type": "video",
            "video": {"type": "external", "external": {"url": post["media_url"]}},
        })
    elif post["type"] == "Podcast" and post.get("media_url"):
        blocks.append({
            "object": "block",
            "type": "audio",
            "audio": {"type": "external", "external": {"url": post["media_url"]}},
        })

    blocks.extend(description_to_blocks(post.get("description", "")))
    return blocks


# ==========================================================================
# Notion create / purge
# ==========================================================================

def _safe_select(value, limit=100):
    cleaned = (value or "").replace(",", "").strip()
    return cleaned[:limit] if cleaned else None


def create_post(post):
    title = post["title"][:2000]
    print(f"  + [{post['type']}] {title}")

    properties = {
        "Title": {"title": [{"text": {"content": title}}]},
        "URL": {"url": post["link"]},
        "Published": {"date": {"start": convert_date(post["published"])}},
    }

    channel = _safe_select(post.get("channel"))
    if channel:
        properties["Channel"] = {"select": {"name": channel}}

    category = _safe_select(post.get("category"))
    if category:
        properties["Category"] = {"select": {"name": category}}

    if post.get("type"):
        properties["Type"] = {"select": {"name": post["type"]}}

    args = {
        "parent": {"data_source_id": DATA_SOURCE_ID},
        "properties": properties,
    }

    if post.get("thumbnail"):
        args["cover"] = {"type": "external", "external": {"url": post["thumbnail"]}}

    blocks = build_blocks(post)
    if blocks:
        args["children"] = blocks[:100]

    page = notion.pages.create(**args)

    if len(blocks) > 100:
        for i in range(100, len(blocks), 100):
            try:
                notion.blocks.children.append(
                    block_id=page["id"], children=blocks[i:i + 100]
                )
            except Exception as e:
                print(f"    block append error at {i}: {e}")


def purge_database():
    print("Archiving existing pages...")
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
                print(f"  archive error: {e}")
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    print(f"Archived {count} pages")


# ==========================================================================
# Main
# ==========================================================================

def run_source(label, url, normalize, name, category):
    print(f"\n=== {label}: {name} ({category}) ===")
    content = fetch_feed_bytes(url)
    if not content:
        print(f"  fetch failed: {url}")
        return []

    feed = feedparser.parse(content)
    if not feed.entries:
        print("  empty feed")
        return []

    posts = normalize(feed, name, category)
    print(f"  today's entries: {len(posts)}")
    return posts


def main():
    today = today_start_vn().strftime("%Y-%m-%d")
    print(f"Sync window: today (VN) = {today}")

    purge_database()

    seen = set()
    total = 0

    for channel_id, category, name in YOUTUBE_CHANNELS:
        posts = run_source(
            "YouTube",
            yt_channel_feed_url(channel_id),
            normalize_youtube_entries,
            name,
            category,
        )
        for p in posts:
            if p["link"] in seen:
                continue
            try:
                create_post(p)
                seen.add(p["link"])
                total += 1
            except Exception as e:
                print(f"  ERROR creating: {e}")
        time.sleep(0.3)

    for feed_url, category, name in PODCAST_FEEDS:
        posts = run_source(
            "Podcast",
            feed_url,
            normalize_podcast_entries,
            name,
            category,
        )
        for p in posts:
            if p["link"] in seen:
                continue
            try:
                create_post(p)
                seen.add(p["link"])
                total += 1
            except Exception as e:
                print(f"  ERROR creating: {e}")
        time.sleep(0.3)

    print(f"\nSync completed: {total} entries for {today}")


if __name__ == "__main__":
    main()
