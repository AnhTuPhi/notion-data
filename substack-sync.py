import feedparser
import os

from notion_client import Client
from datetime import datetime


RSS_URLS = [
    "https://bachhoavienvong.substack.com/feed"
]


DATABASE_ID = os.environ["DATABASE_ID"]

notion = Client(
    auth=os.environ["NOTION_TOKEN"]
)


SYNC_FILE = "synced_posts.txt"


# Load already synced URLs
if os.path.exists(SYNC_FILE):

    with open(SYNC_FILE, "r") as f:
        synced_posts = set(
            line.strip()
            for line in f.readlines()
        )

else:
    synced_posts = set()



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

                    "start":
                    datetime.now().isoformat()

                }

            },


            "Source": {

                "select": {

                    "name": source

                }

            }


        },


        children=[

            {

                "object": "block",

                "type": "paragraph",

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



for rss_url in RSS_URLS:


    print("====================")

    print(
        "Fetching:",
        rss_url
    )


    feed = feedparser.parse(
        rss_url
    )


    print(
        "Found posts:",
        len(feed.entries)
    )



    for post in feed.entries:


        print(
            "Checking:",
            post.title
        )


        if post.link in synced_posts:


            print(
                "Already synced:",
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



# Save state

with open(
    SYNC_FILE,
    "w"
) as f:


    for url in sorted(
        synced_posts
    ):

        f.write(
            url + "\n"
        )


print("Sync completed")