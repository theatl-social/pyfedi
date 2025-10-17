# Communities as ActivityPub 'Group' Actors

The communities that make up the heart of the "threadiverse" are represented as ActivityPub Group Actors. As such they are implemented to follow [FEP-1b12: Group federation](https://codeberg.org/fediverse/fep/src/branch/main/fep/1b12/fep-1b12.md)


## Group objects as JSON

Server-to-server or server-to-client traffic that represents Communities is sent as .json. I.e. when a remote server wishes to find out information about your local server's `technology` community, the remote server will be sent that data in a json payload.


### Getting community information

Piefed internally keeps track of communities in a database, but you can query the information from the server as .json. There are many ways to do so, but here is an example using `curl`.

We will use the https://piefed.social flagship instance in the example. We will ask for information about the `piefed_meta` community.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/c/piefed_meta
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attributedTo": "https://piefed.social/c/piefed_meta/moderators",
    "endpoints": {
        "sharedInbox": "https://piefed.social/inbox"
    },
    "featured": "https://piefed.social/c/piefed_meta/featured",
    "followers": "https://piefed.social/c/piefed_meta/followers",
    "icon": {
        "type": "Image",
        "url": "https://piefed.social/static/media/communities/HG/yB/HGyB58LEAHeHwdN.png"
    },
    "id": "https://piefed.social/c/piefed_meta",
    "inbox": "https://piefed.social/c/piefed_meta/inbox",
    "moderators": "https://piefed.social/c/piefed_meta/moderators",
    "name": "PieFed Meta",
    "newModsWanted": false,
    "outbox": "https://piefed.social/c/piefed_meta/outbox",
    "postingRestrictedToMods": false,
    "preferredUsername": "piefed_meta",
    "privateMods": false,
    "publicKey": {
        "id": "https://piefed.social/c/piefed_meta#main-key",
        "owner": "https://piefed.social/c/piefed_meta",
        "publicKeyPem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAm694+pAd9VdRWjsb84u0\nWGoAI7d/riiQVC5GHHgDJX4EYqTD1tvD2kB3URsHGgj4lf8pCHrjXHk/H3CpogRc\nOwyJ+ZLHrXYKyPz8r9SO0sR8KbM3tfD7EXhDLjgsK91gzPxvQ9OLneghb1n0uSmn\n4cWxbbdebDsB+jyPcF37KkSayAYwkaAjwb2nVNgxLN0w7J3ENnhpO/F6FpOBJEx1\nAHEfstlhHl6Cd2PfLFMiW4hYaryeJNMnGxE2ZqE6JGeRTikY7+ZbiG/Rx6OLXM8v\nAx/92BwQSnIEDIPsLyHOH2fFhfrtlNTA740ujq5mUjeBUz11ueGEn9GwZ5JrVc6S\nxQIDAQAB\n-----END PUBLIC KEY-----\n"
    },
    "published": "2024-01-04T08:55:20.668181+00:00",
    "sensitive": false,
    "source": {
        "content": "Discuss PieFed project direction, provide feedback, ask questions, suggest improvements, and engage in conversations related to the platform organization, policies, features, and community dynamics.\r\n\r\n## [Wiki](https://piefed.social/community/piefed_meta/wiki/index)",
        "mediaType": "text/markdown"
    },
    "summary": "<p>Discuss PieFed project direction, provide feedback, ask questions, suggest improvements, and engage in conversations related to the platform organization, policies, features, and community dynamics.</p>\n<h2><a href=\"https://piefed.social/community/piefed_meta/wiki/index\" rel=\"nofollow ugc\" target=\"\">Wiki</a></h2>\n",
    "type": "Group",
    "updated": "2024-11-12T05:01:43.466282+00:00",
    "url": "https://piefed.social/c/piefed_meta"
}
```

### Getting the posts

Now that we have the communities object we can parse it for the information we want. Since this is the threadiverse we are mostly wanting the posts in the community.

Those can be found by requesting the actors `outbox`.


Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/c/piefed_meta/outbox
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "orderedItems": [...],
    "id": "https://piefed.social/c/piefed_meta/outbox",
    "totalItems": 50,
    "type": "OrderedCollection"
}
```

The `oderedItems` list will be a list of [Announce](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-announce) activities that have wrap Objects that represent the activity in the community. Usually these are [Create](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-create) activity objects for [Page](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-page), [Article](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-article), [Link](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-link), [Note](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-note), or [Question](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-question) objects.


Here is an example `Announce` object, wrapping a `Create` object, that creates a `Page` object. On the web it looks like [this](https://piefed.social/post/317673), and in .json it looks like:
```json
    {
        "actor": "https://piefed.social/c/piefed_meta",
        "cc": [
            "https://piefed.social/c/piefed_meta/followers"
        ],
        "id": "https://piefed.social/activities/announce/CEgCNWWTDQc3ZZ8",
        "object": {
            "actor": "https://piefed.social/u/rimu",
            "audience": "https://piefed.social/c/piefed_meta",
            "cc": [
                "https://piefed.social/c/piefed_meta"
            ],
            "id": "https://piefed.social/activities/create/oesyDhuiRuQ3wNZ",
            "object": {
                "attachment": [],
                "attributedTo": "https://piefed.social/u/rimu",
                "audience": "https://piefed.social/c/piefed_meta",
                "cc": [],
                "commentsEnabled": true,
                "content": "<p>Key updates include the addition of community icons for better identification, a notification management interface, and various enhancements to our API for eventual mobile app support. Below is a detailed overview of the changes we've made.</p>\n<h2>Jeena</h2>\n<ul>\n<li>Community icon alongside name in post teaser. This helps differentiate between communities with the same name and adds visual interest.</li>\n</ul>\n<h2>Freamon</h2>\n<ul>\n<li>Added a notification management interface to manage notifications from all the communities and posts you are subscribed to - <a href=\"https://piefed.social/alerts\" rel=\"nofollow ugc\" target=\"_blank\">https://piefed.social/alerts</a></li>\n<li>Soft deletion of comments, so they can be un-deleted again.</li>\n<li>Lots of API work for the mobile app. Lots!</li>\n</ul>\n<h1>Rimu</h1>\n<ul>\n<li>Generate YouTube thumbnails more reliably.</li>\n<li>Instance overview pages which make it easy to see posts and people from any instance. Start exploring at <a href=\"https://piefed.social/instances\" rel=\"nofollow ugc\" target=\"_blank\">https://piefed.social/instances</a>.</li>\n<li>FEP-268d: Search consent signals for objects. This FEP is a convention for how instances can signal to other instances which posts should be searchable.</li>\n<li>Track who deleted which posts, for accountability among moderators.</li>\n<li>Refactoring to support API work by Freamon.</li>\n<li>Automatically delete voting data older than 6 months (aggregated totals are unaffected). Voting data consumes gigabytes of space and it only meaningfully affects ranking of posts in the first few days. The only other reason to keep this data is for vote manipulation analysis and 6 months worth of data should be plenty.</li>\n<li>Instances with open registrations automatically close registrations after one week of having no admins log in. This will avoid abandoned instances becoming a vector for spam or a home of trolls.</li>\n<li>Show instance name after display name. If you notice undesirable patterns of behaviour associated with certain instances you can block the whole instance.</li>\n<li>Improve visibility of user-level instance blocking functionality. This is separate and in addition to defederation which is controlled by admins.</li>\n<li>Display PeerTube licence info on video posts. This could be rolled out to other post types in future?</li>\n<li>Topics now have an option to show posts from communities that are in child topics. E.g. <a href=\"https://piefed.social/topic/arts-craft\" rel=\"nofollow ugc\" target=\"_blank\">https://piefed.social/topic/arts-craft</a> only has two communities in it so the number of posts shown there is very low. However it\u2019s child topics (Arts, Craft and Photography) have quite a few communities so to populate the top-level topic it makes sense to display posts from all the child topics too. <a href=\"https://piefed.social/topic/tech/programming\" rel=\"nofollow ugc\" target=\"_blank\">https://piefed.social/topic/tech/programming</a> is a similar case.</li>\n</ul>\n<p>--</p>\n<p>As a free and open source project, PieFed receives no funding and developers are not paid. Any donations you can spare will help cover server and infrastructure costs - <a href=\"https://piefed.social/donate\" rel=\"nofollow ugc\" target=\"_blank\">https://piefed.social/donate</a>. Thanks!</p>\n",
                "id": "https://piefed.social/post/317673",
                "language": {
                    "identifier": "en",
                    "name": "English"
                },
                "mediaType": "text/html",
                "name": "PieFed development update Oct/Nov 2024",
                "published": "2024-11-09T00:36:19.078892+00:00",
                "replies": [
                    {
                        "@context": [
                            "https://www.w3.org/ns/activitystreams",
                            "https://w3id.org/security/v1"
                        ],
                        "attributedTo": "https://piefed.social/u/imaqtpie",
                        "audience": "https://piefed.social/c/piefed_meta",
                        "cc": [
                            "https://piefed.social/c/piefed_meta",
                            "https://piefed.social/u/imaqtpie/followers"
                        ],
                        "content": "<p>Good work! Much thanks to all contributors, you are appreciated. The site is running smooth and looking great.</p>\n",
                        "distinguished": false,
                        "id": "https://piefed.social/comment/3526458",
                        "inReplyTo": "https://piefed.social/post/317673",
                        "language": {
                            "identifier": "en",
                            "name": "English"
                        },
                        "mediaType": "text/html",
                        "published": "2024-11-09T03:55:50.533858+00:00",
                        "source": {
                            "content": "Good work! Much thanks to all contributors, you are appreciated. The site is running smooth and looking great.",
                            "mediaType": "text/markdown"
                        },
                        "to": [
                            "https://www.w3.org/ns/activitystreams#Public",
                            "https://piefed.social/u/rimu"
                        ],
                        "type": "Note"
                    }
                ],
                "searchableBy": "https://www.w3.org/ns/activitystreams#Public",
                "sensitive": false,
                "source": {
                    "content": "Key updates include the addition of community icons for better identification, a notification management interface, and various enhancements to our API for eventual mobile app support. Below is a detailed overview of the changes we've made.\r\n\r\n##Jeena\r\n\r\n- Community icon alongside name in post teaser. This helps differentiate between communities with the same name and adds visual interest.\r\n\r\n##Freamon\r\n\r\n- Added a notification management interface to manage notifications from all the communities and posts you are subscribed to - https://piefed.social/alerts\r\n- Soft deletion of comments, so they can be un-deleted again.\r\n- Lots of API work for the mobile app. Lots!\r\n\r\n#Rimu\r\n\r\n- Generate YouTube thumbnails more reliably.\r\n- Instance overview pages which make it easy to see posts and people from any instance. Start exploring at https://piefed.social/instances.\r\n- FEP-268d: Search consent signals for objects. This FEP is a convention for how instances can signal to other instances which posts should be searchable.\r\n- Track who deleted which posts, for accountability among moderators.\r\n- Refactoring to support API work by Freamon.\r\n- Automatically delete voting data older than 6 months (aggregated totals are unaffected). Voting data consumes gigabytes of space and it only meaningfully affects ranking of posts in the first few days. The only other reason to keep this data is for vote manipulation analysis and 6 months worth of data should be plenty.\r\n- Instances with open registrations automatically close registrations after one week of having no admins log in. This will avoid abandoned instances becoming a vector for spam or a home of trolls.\r\n- Show instance name after display name. If you notice undesirable patterns of behaviour associated with certain instances you can block the whole instance.\r\n- Improve visibility of user-level instance blocking functionality. This is separate and in addition to defederation which is controlled by admins.\r\n- Display PeerTube licence info on video posts. This could be rolled out to other post types in future?\r\n- Topics now have an option to show posts from communities that are in child topics. E.g. https://piefed.social/topic/arts-craft only has two communities in it so the number of posts shown there is very low. However it\u2019s child topics (Arts, Craft and Photography) have quite a few communities so to populate the top-level topic it makes sense to display posts from all the child topics too. https://piefed.social/topic/tech/programming is a similar case.\r\n\r\n\r\n--\r\n\r\nAs a free and open source project, PieFed receives no funding and developers are not paid. Any donations you can spare will help cover server and infrastructure costs - https://piefed.social/donate. Thanks!",
                    "mediaType": "text/markdown"
                },
                "stickied": false,
                "tag": [
                    {
                        "href": "https://piefed.social/tag/fediverse",
                        "name": "#fediverse",
                        "type": "Hashtag"
                    },
                    {
                        "href": "https://piefed.social/tag/piefed",
                        "name": "#piefed",
                        "type": "Hashtag"
                    }
                ],
                "to": [
                    "https://piefed.social/c/piefed_meta",
                    "https://www.w3.org/ns/activitystreams#Public"
                ],
                "type": "Page"
            },
            "to": [
                "https://www.w3.org/ns/activitystreams#Public"
            ],
            "type": "Create"
        },
        "to": [
            "https://www.w3.org/ns/activitystreams#Public"
        ],
        "type": "Announce"
    }

```
