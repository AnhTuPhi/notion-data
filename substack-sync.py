import feedparser
import os

from notion_client import Client
from datetime import datetime


RSS_URLS = [
    "https://newsletter.pragmaticengineer.com/feed",
    "https://thealgorithm.substack.com/feed",
    "https://bachhoavienvong.substack.com/feed"
]


notion = Client(
    auth=os.environ["NOTION_TOKEN"]
)


DATABASE_ID = os.environ["DATABASE_ID"]


def exists(url):

    result = notion.databases.query(
        database_id=DATABASE_ID,
        filter={
            "property": "URL",
            "url": {
                "equals": url
            }
        }
    )

    return len(result["results"]) > 0



def create_post(post, source):

    print("Creating:", post.title)

    notion.pages.create(

        parent={
            "database_id": DATABASE_ID
        },

        properties={

            "Title": {
                "title": [
                    {
                        "text": {
                            "content": post.title
                        }
                    }
                ]
            },


            "URL": {
                "url": post.link
            },


            "Published": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            },


            "Source": {
                "select": {
                    "name": source
                }
            }

        }
    )



for rss_url in RSS_URLS:

    print("====================")
    print("Fetching:", rss_url)


    feed = feedparser.parse(rss_url)


    print(
        "Found posts:",
        len(feed.entries)
    )


    for post in feed.entries:


        print(
            "Checking:",
            post.title
        )


        if exists(post.link):

            print(
                "Skip existing:",
                post.title
            )

            continue


        create_post(
            post,
            rss_url
        )