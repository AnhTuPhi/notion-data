import os
import requests
import feedparser

from notion_client import Client
from datetime import datetime


RSS_URLS = [
    "https://newsletter.pragmaticengineer.com/feed",
    "https://bachhoavienvong.substack.com/feed",
]


DATABASE_ID = os.environ["DATABASE_ID"]

NOTION_TOKEN = os.environ["NOTION_TOKEN"]


notion = Client(
    auth=NOTION_TOKEN
)


SYNC_FILE = "synced_posts.txt"


# =========================
# Load synced URLs
# =========================

if os.path.exists(SYNC_FILE):

    with open(SYNC_FILE, "r", encoding="utf-8") as f:

        synced_posts = set(
            x.strip()
            for x in f.readlines()
        )

else:

    synced_posts = set()



# =========================
# Fetch RSS
# =========================

def fetch_feed(url):

    print("Fetching RSS:", url)


    headers = {

        "User-Agent":
        "Mozilla/5.0 (X11; Linux x86_64)",

        "Accept":
        "application/rss+xml, application/xml, text/xml"

    }


    response = requests.get(

        url,

        headers=headers,

        timeout=30

    )


    print(
        "HTTP:",
        response.status_code
    )


    print(
        "Content:",
        response.text[:100]
    )


    return feedparser.parse(
        response.content
    )



# =========================
# Create Notion Page
# =========================

def create_post(post, source):


    print(
        "Creating:",
        post.title
    )


    published = post.get(
        "published",
        datetime.now().isoformat()
    )


    notion.pages.create(

        parent={

            "database_id":
            DATABASE_ID

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

            },


            "Source": {

                "rich_text": [

                    {

                        "text": {

                            "content":
                            source

                        }

                    }

                ]

            }


        },


        children=[

            {

                "object":
                "block",

                "type":
                "paragraph",

                "paragraph": {

                    "rich_text": [

                        {

                            "text": {

                                "content":
                                post.get(
                                    "summary",
                                    ""
                                )[:1500]

                            }

                        }

                    ]

                }

            }

        ]

    )



# =========================
# Main sync
# =========================


for rss_url in RSS_URLS:


    print("====================")


    feed = fetch_feed(
        rss_url
    )


    print(
        "Found posts:",
        len(feed.entries)
    )


    print(
        "Feed error:",
        feed.bozo
    )


    if feed.bozo:

        print(
            feed.bozo_exception
        )



    for post in feed.entries:


        print(
            "Checking:",
            post.title
        )


        if post.link in synced_posts:


            print(
                "Skip:",
                post.title
            )

            continue



        try:


            create_post(
                post,
                rss_url
            )


            synced_posts.add(
                post.link
            )


            print(
                "Done:",
                post.title
            )


        except Exception as e:


            print(
                "ERROR:",
                e
            )



# =========================
# Save state
# =========================


with open(
    SYNC_FILE,
    "w",
    encoding="utf-8"
) as f:


    for url in sorted(
        synced_posts
    ):

        f.write(
            url + "\n"
        )



print(
    "Sync completed"
)