import os
import json
import time
import feedparser
import cloudscraper

from urllib.parse import urlparse
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup, NavigableString
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


WARP_PROXY = os.environ.get("WARP_PROXY", "").strip() or None


def _proxies():
    if WARP_PROXY:
        return {"http": WARP_PROXY, "https": WARP_PROXY}
    return None


if WARP_PROXY:
    print(f"Using WARP proxy: {WARP_PROXY}")
else:
    print("No WARP_PROXY set; using direct connection")


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


def _peek(content):
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return ""
    return text[:200].replace("\n", " ")


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
        r = scraper.get(
            url,
            headers=BROWSER_HEADERS,
            timeout=30,
            proxies=_proxies(),
        )
        if r.status_code == 200:
            return r.content
        print(f"  cloudscraper HTTP {r.status_code} | {_peek(r.content)}")
    except Exception as e:
        print(f"  cloudscraper error: {e}")
    return None


# ---------- Paywall + metadata helpers ----------

PAYWALL_PHRASES = [
    "this post is for paid subscribers",
    "this post is for paying subscribers",
    "this post is for subscribers",
    "subscribe to keep reading",
    "is only available to paid subscribers",
    "this episode is for paid subscribers",
]


def is_paywalled_html(html):
    if not html:
        return False
    text = BeautifulSoup(html, "html.parser").get_text(
        separator=" ", strip=True
    ).lower()
    return any(phrase in text for phrase in PAYWALL_PHRASES)


def derive_source_name(url):
    host = urlparse(url).netloc.replace("www.", "")
    if host.endswith(".substack.com"):
        return host.replace(".substack.com", "")
    return host


def extract_first_image(html):
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    img = soup.find("img")
    if img:
        src = img.get("src") or img.get("data-src")
        if src and src.startswith(("http://", "https://")):
            return src
    return None


# ---------- HTML -> Notion blocks converter ----------

def _make_text(content, ann=None, link=None):
    obj = {"type": "text", "text": {"content": content[:2000]}}
    if link:
        obj["text"]["link"] = {"url": link}
    if ann:
        obj["annotations"] = {
            "bold": ann.get("bold", False),
            "italic": ann.get("italic", False),
            "underline": ann.get("underline", False),
            "strikethrough": ann.get("strikethrough", False),
            "code": ann.get("code", False),
            "color": "default",
        }
    return obj


def _inline_to_rt(element, ann=None, link=None):
    if ann is None:
        ann = {}

    if isinstance(element, NavigableString):
        text = str(element)
        if text:
            return [_make_text(text, ann, link)]
        return []

    new_ann = dict(ann)
    new_link = link
    name = getattr(element, "name", None)

    if name in ("strong", "b"):
        new_ann["bold"] = True
    elif name in ("em", "i"):
        new_ann["italic"] = True
    elif name == "u":
        new_ann["underline"] = True
    elif name in ("s", "strike", "del"):
        new_ann["strikethrough"] = True
    elif name == "code":
        new_ann["code"] = True
    elif name == "a":
        href = element.get("href")
        if href and href.startswith(("http://", "https://")):
            new_link = href
    elif name == "br":
        return [_make_text("\n", ann, link)]

    result = []
    for child in element.children:
        result.extend(_inline_to_rt(child, new_ann, new_link))
    return result


def _chunk_rt(rt):
    """Split items > 2000 chars and cap array length to 100."""
    out = []
    for item in rt:
        content = item.get("text", {}).get("content", "")
        if len(content) <= 2000:
            out.append(item)
        else:
            for i in range(0, len(content), 2000):
                copy = json.loads(json.dumps(item))
                copy["text"]["content"] = content[i:i + 2000]
                out.append(copy)
    return out[:100]


def _rt_nonempty(rt):
    return any(it.get("text", {}).get("content", "").strip() for it in rt)


def _block(typ, payload):
    return {"object": "block", "type": typ, typ: payload}


def _paragraph(rt):
    return _block("paragraph", {"rich_text": _chunk_rt(rt)})


def _convert_elem(elem):
    if isinstance(elem, NavigableString):
        text = str(elem).strip()
        if text:
            return [_paragraph([_make_text(text)])]
        return []

    name = getattr(elem, "name", None)
    if name is None:
        return []

    if name == "p":
        rt = _inline_to_rt(elem)
        return [_paragraph(rt)] if _rt_nonempty(rt) else []

    if name in ("h1", "h2"):
        rt = _inline_to_rt(elem)
        return [_block("heading_2", {"rich_text": _chunk_rt(rt)})] if _rt_nonempty(rt) else []

    if name in ("h3", "h4", "h5", "h6"):
        rt = _inline_to_rt(elem)
        return [_block("heading_3", {"rich_text": _chunk_rt(rt)})] if _rt_nonempty(rt) else []

    if name == "ul":
        blocks = []
        for li in elem.find_all("li", recursive=False):
            rt = _inline_to_rt(li)
            if _rt_nonempty(rt):
                blocks.append(_block("bulleted_list_item", {"rich_text": _chunk_rt(rt)}))
        return blocks

    if name == "ol":
        blocks = []
        for li in elem.find_all("li", recursive=False):
            rt = _inline_to_rt(li)
            if _rt_nonempty(rt):
                blocks.append(_block("numbered_list_item", {"rich_text": _chunk_rt(rt)}))
        return blocks

    if name == "blockquote":
        rt = _inline_to_rt(elem)
        return [_block("quote", {"rich_text": _chunk_rt(rt)})] if _rt_nonempty(rt) else []

    if name == "img":
        src = elem.get("src") or elem.get("data-src")
        if src and src.startswith(("http://", "https://")):
            return [_block("image", {"type": "external", "external": {"url": src}})]
        return []

    if name == "pre":
        code_elem = elem.find("code")
        text = code_elem.get_text() if code_elem else elem.get_text()
        return [_block("code", {
            "rich_text": [_make_text(text)],
            "language": "plain text",
        })]

    if name == "hr":
        return [_block("divider", {})]

    if name in ("div", "figure", "section", "article", "main"):
        blocks = []
        for child in elem.children:
            blocks.extend(_convert_elem(child))
        return blocks

    if name == "figcaption":
        rt = _inline_to_rt(elem)
        return [_paragraph(rt)] if _rt_nonempty(rt) else []

    # Default: treat unknown tag's inline content as a paragraph
    rt = _inline_to_rt(elem)
    return [_paragraph(rt)] if _rt_nonempty(rt) else []


def html_to_blocks(html):
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"  html parse error: {e}")
        return []
    blocks = []
    for elem in soup.children:
        blocks.extend(_convert_elem(elem))
    return blocks


# ---------- Normalize feed entries ----------

def normalize_feedparser(feed, source):
    posts = []
    for e in feed.entries:
        link = e.get("link", "")
        if not link:
            continue

        author = e.get("author", "")
        if not author:
            authors = e.get("authors", []) or []
            if authors:
                author = authors[0].get("name", "")

        content_html = ""
        contents = getattr(e, "content", None)
        if contents:
            content_html = contents[0].value
        elif e.get("summary"):
            content_html = e.summary

        cover = extract_first_image(content_html)

        posts.append({
            "title": e.get("title", "(untitled)"),
            "link": link,
            "published": e.get("published", ""),
            "author": author,
            "source": source,
            "content_html": content_html,
            "cover": cover,
        })
    return posts


def normalize_substack_api(content, source):
    data = json.loads(content)
    posts = []
    for p in data:
        link = p.get("canonical_url") or p.get("url", "")
        if not link:
            continue

        audience = p.get("audience", "everyone")
        if audience in ("only_paid", "founding"):
            print(f"  paywall skip (api audience={audience}): {p.get('title', '')}")
            continue

        bylines = p.get("publishedBylines") or p.get("contributors") or []
        author = bylines[0].get("name", "") if bylines else ""

        content_html = p.get("body_html") or p.get("description") or ""
        cover = p.get("cover_image") or extract_first_image(content_html)

        posts.append({
            "title": p.get("title", "(untitled)"),
            "link": link,
            "published": p.get("post_date") or "",
            "author": author,
            "source": source,
            "content_html": content_html,
            "cover": cover,
        })
    return posts


def fetch_posts(url):
    source_fallback = derive_source_name(url)

    content = try_curl_cffi(url)
    if content:
        feed = feedparser.parse(content)
        if feed.entries:
            feed_title = feed.feed.get("title", "") if getattr(feed, "feed", None) else ""
            return normalize_feedparser(feed, feed_title or source_fallback)
        print("  curl_cffi: empty feed")

    content = try_cloudscraper(url)
    if content:
        feed = feedparser.parse(content)
        if feed.entries:
            feed_title = feed.feed.get("title", "") if getattr(feed, "feed", None) else ""
            return normalize_feedparser(feed, feed_title or source_fallback)
        print("  cloudscraper: empty feed")

    if ".substack.com" in url:
        base = url.rsplit("/feed", 1)[0]
        api = f"{base}/api/v1/archive?sort=new&limit=20"
        print(f"  fallback API: {api}")
        content = try_curl_cffi(api)
        if content:
            try:
                return normalize_substack_api(content, source_fallback)
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
        return datetime.fromisoformat(published.replace("Z", "+00:00")).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


# ---------- Notion create ----------

def create_post(post):
    title = post["title"][:2000]
    print("Creating:", title)

    properties = {
        "Title": {"title": [{"text": {"content": title}}]},
        "URL": {"url": post["link"]},
        "Published": {"date": {"start": convert_date(post["published"])}},
    }

    if post.get("author"):
        properties["Author"] = {
            "rich_text": [{"text": {"content": post["author"][:2000]}}]
        }

    if post.get("source"):
        properties["Source"] = {"select": {"name": post["source"][:100]}}

    args = {
        "parent": {"data_source_id": DATA_SOURCE_ID},
        "properties": properties,
    }

    if post.get("cover"):
        args["cover"] = {"type": "external", "external": {"url": post["cover"]}}

    blocks = html_to_blocks(post.get("content_html", ""))

    if blocks:
        args["children"] = blocks[:100]

    page = notion.pages.create(**args)

    if len(blocks) > 100:
        for i in range(100, len(blocks), 100):
            chunk = blocks[i:i + 100]
            try:
                notion.blocks.children.append(block_id=page["id"], children=chunk)
            except Exception as e:
                print(f"  block append error at offset {i}: {e}")


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

        if is_paywalled_html(post.get("content_html", "")):
            print("Paywall skip:", post["title"])
            continue

        try:
            create_post(post)
            seen_links.add(post["link"])
        except Exception as e:
            print("ERROR:", e)

    time.sleep(1)


print("Sync completed:", len(seen_links), "posts")
