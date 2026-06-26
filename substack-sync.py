import feedparser
import os
from notion_client import Client
from datetime import datetime


RSS_URL = "https://bachhoavienvong.substack.com/feed"

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



def create_post(post):

    notion.pages.create(
        parent={
            "database_id": DATABASE_ID
        },

        properties={

            "Title":{
                "title":[
                    {
                        "text":{
                            "content":post.title
                        }
                    }
                ]
            },

            "URL":{
                "url":post.link
            },

            "Published":{
                "date":{
                    "start":datetime.now().isoformat()
                }
            }

        },


        children=[

            {
                "object":"block",
                "type":"paragraph",

                "paragraph":{
                    "rich_text":[
                        {
                            "text":{
                                "content":
                                post.summary[:1800]
                            }
                        }
                    ]
                }
            }

        ]
    )


feed = feedparser.parse(RSS_URL)


for post in feed.entries:
    if exists(post.link):
        continue
    print("Sync:", post.title)
    create_post(post)