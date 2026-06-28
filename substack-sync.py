import os
import requests
import feedparser

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
    "https://blackswain.substack.com/feed",
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
    "https://zoedatalens.substack.com/feed",
    "https://vutuyen.substack.com/feed",
    "https://vnwyckoffclub.substack.com/feed",
    "https://vnhacker.substack.com/feed",
    "https://vohoanghac.com/feed"
]


DATABASE_ID = os.environ["DATABASE_ID"]

notion = Client(
    auth=os.environ["NOTION_TOKEN"]
)


SYNC_FILE = "synced_posts.txt"



if os.path.exists(SYNC_FILE):

    with open(SYNC_FILE, encoding="utf-8") as f:
        synced_posts = set(
            x.strip()
            for x in f.readlines()
        )

else:
    synced_posts = set()



def fetch_feed(url):

    headers = {
        "User-Agent":
        "Mozilla/5.0",
        "Accept":
        "application/rss+xml,text/xml"
    }


    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )


    print("HTTP:", response.status_code)


    if response.status_code != 200:

        print(
            "Skip RSS:",
            url
        )

        return None


    return feedparser.parse(
        response.content
    )



def convert_date(post):

    raw = post.get(
        "published"
    )


    if not raw:
        return datetime.utcnow().isoformat()


    try:

        dt = parsedate_to_datetime(
            raw
        )

        return dt.isoformat()


    except Exception:

        return datetime.utcnow().isoformat()



def create_post(post):


    published = convert_date(post)


    print(
        "Creating:",
        post.title
    )


    notion.pages.create(

        parent={
            "database_id": DATABASE_ID
        },


        properties={


            "Title": {

                "title": [

                    {
                        "text": {
                            "content":
                            post.title
                        }
                    }

                ]

            },


            "URL": {

                "url":
                post.link

            },


            "Published": {

                "date": {

                    "start":
                    published

                }

            }
        }

    )



for rss_url in RSS_URLS:


    print("====================")

    print(
        "Fetching:",
        rss_url
    )


    feed = fetch_feed(
        rss_url
    )


    if feed is None:
        continue


    print(
        "Found:",
        len(feed.entries)
    )


    for post in feed.entries:


        if post.link in synced_posts:

            print(
                "Skip:",
                post.title
            )

            continue



        try:

            create_post(
                post
            )


            synced_posts.add(
                post.link
            )


        except Exception as e:

            print(
                "ERROR:",
                e
            )



with open(
    SYNC_FILE,
    "w",
    encoding="utf-8"
) as f:

    for url in synced_posts:

        f.write(
            url + "\n"
        )


print(
    "Sync completed"
)
