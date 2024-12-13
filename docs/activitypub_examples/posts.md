# Posts as ActivityPub Objects

Piefed has the following kinds of posts for communities.

## Discussion / Page

This is a discussion post on the web: https://piefed.social/post/342105

You can also see it represented as a `Page` object in .json format.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/post/342105
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attachment": [],
    "attributedTo": "https://jolly-piefed.jomandoa.net/u/jollyroberts",
    "audience": "https://piefed.social/c/playground",
    "cc": [],
    "commentsEnabled": true,
    "content": "<p>Example Discussion Post Body</p>\n",
    "id": "https://jolly-piefed.jomandoa.net/post/79757",
    "language": {
        "identifier": "en",
        "name": "English"
    },
    "mediaType": "text/html",
    "name": "Example Discussion Post Title",
    "published": "2024-11-24T22:18:50.230305+00:00",
    "replies": [],
    "sensitive": false,
    "source": {
        "content": "Example Discussion Post Body",
        "mediaType": "text/markdown"
    },
    "stickied": false,
    "tag": [
        {
            "href": "https://piefed.social/tag/tagone",
            "name": "#tagone",
            "type": "Hashtag"
        },
        {
            "href": "https://piefed.social/tag/tagtwo",
            "name": "#tagtwo",
            "type": "Hashtag"
        }
    ],
    "to": [
        "https://piefed.social/c/playground",
        "https://www.w3.org/ns/activitystreams#Public"
    ],
    "type": "Page"
}

```

## Link / Page

This is a link post on the web: https://piefed.social/post/342122

You can also see it represented as a `Page` object in .json format.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/post/342122
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attachment": [
        {
            "href": "https://www.w3.org/TR/activitystreams-vocabulary",
            "type": "Link"
        }
    ],
    "attributedTo": "https://jolly-piefed.jomandoa.net/u/jollyroberts",
    "audience": "https://piefed.social/c/playground",
    "cc": [],
    "commentsEnabled": true,
    "content": "<p>Example Link Post Body</p>\n",
    "id": "https://jolly-piefed.jomandoa.net/post/79771",
    "language": {
        "identifier": "en",
        "name": "English"
    },
    "mediaType": "text/html",
    "name": "Example Link Post Title",
    "published": "2024-11-24T22:34:56.000879+00:00",
    "replies": [],
    "sensitive": false,
    "source": {
        "content": "Example Link Post Body",
        "mediaType": "text/markdown"
    },
    "stickied": false,
    "tag": [
        {
            "href": "https://piefed.social/tag/tagone",
            "name": "#tagone",
            "type": "Hashtag"
        },
        {
            "href": "https://piefed.social/tag/tagtwo",
            "name": "#tagtwo",
            "type": "Hashtag"
        }
    ],
    "to": [
        "https://piefed.social/c/playground",
        "https://www.w3.org/ns/activitystreams#Public"
    ],
    "type": "Page"
}
```


## Image / Page

This is a image post on the web: https://piefed.social/post/342166

You can also see it represented as a `Page` object in .json format.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/post/342166
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attachment": [
        {
            "name": "a painting of a crystal flower, AI art, stable diffusion",
            "type": "Image",
            "url": "https://jolly-piefed.jomandoa.net/static/media/posts/Ef/lI/EflI4MtZdsQDOUP.png"
        }
    ],
    "attributedTo": "https://jolly-piefed.jomandoa.net/u/jollyroberts",
    "audience": "https://piefed.social/c/playground",
    "cc": [],
    "commentsEnabled": true,
    "content": "<p>Example Image Post Body</p>\n",
    "id": "https://jolly-piefed.jomandoa.net/post/79799",
    "image": {
        "type": "Image",
        "url": "https://jolly-piefed.jomandoa.net/static/media/posts/Ef/lI/EflI4MtZdsQDOUP.png"
    },
    "language": {
        "identifier": "en",
        "name": "English"
    },
    "mediaType": "text/html",
    "name": "Example Image Post Title",
    "published": "2024-11-24T23:19:37.419801+00:00",
    "replies": [],
    "sensitive": false,
    "source": {
        "content": "Example Image Post Body",
        "mediaType": "text/markdown"
    },
    "stickied": false,
    "tag": [],
    "to": [
        "https://piefed.social/c/playground",
        "https://www.w3.org/ns/activitystreams#Public"
    ],
    "type": "Page"
}
```

## Video / Page

This is a video post on the web: https://piefed.social/post/276328

You can also see it represented as a `Page` object in .json format.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/post/276328
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attachment": [
        {
            "href": "https://files.catbox.moe/swf46b.mp4",
            "type": "Link"
        }
    ],
    "attributedTo": "https://piefed.social/u/Binzy_Boi",
    "audience": "https://piefed.social/c/playground",
    "cc": [],
    "commentsEnabled": true,
    "content": "",
    "id": "https://piefed.social/post/276328",
    "image": {
        "type": "Image",
        "url": "https://files.catbox.moe/swf46b.mp4"
    },
    "language": {
        "identifier": "en",
        "name": "English"
    },
    "mediaType": "text/html",
    "name": "Video post test 3",
    "published": "2024-10-14T00:03:41.660107+00:00",
    "replies": [],
    "sensitive": false,
    "source": {
        "content": "",
        "mediaType": "text/markdown"
    },
    "stickied": false,
    "tag": [],
    "to": [
        "https://piefed.social/c/playground",
        "https://www.w3.org/ns/activitystreams#Public"
    ],
    "type": "Page"
}
```

## Poll / Question

This is a poll post on the web: https://piefed.social/post/341021

You can also see it represented as a `Question` object in .json format.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/post/341021
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attachment": [],
    "attributedTo": "https://jolly-piefed.jomandoa.net/u/jollyroberts",
    "audience": "https://piefed.social/c/playground",
    "cc": [],
    "commentsEnabled": true,
    "content": "<p>this is the poll post body</p>\n",
    "endTime": "2024-11-27T00:47:11.362544+00:00",
    "id": "https://jolly-piefed.jomandoa.net/post/79247",
    "language": {
        "identifier": "en",
        "name": "English"
    },
    "mediaType": "text/html",
    "name": "Poll Post Test",
    "oneOf": [
        {
            "name": "Yes",
            "replies": {
                "totalItems": 2,
                "type": "Collection"
            },
            "type": "Note"
        },
        {
            "name": "No",
            "replies": {
                "totalItems": 0,
                "type": "Collection"
            },
            "type": "Note"
        },
        {
            "name": "Maybe",
            "replies": {
                "totalItems": 0,
                "type": "Collection"
            },
            "type": "Note"
        }
    ],
    "published": "2024-11-24T00:47:11.789789+00:00",
    "replies": [
        {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://w3id.org/security/v1"
            ],
            "attributedTo": "https://hub.netzgemeinde.eu/channel/jupiter_rowland",
            "audience": "https://piefed.social/c/playground",
            "cc": [
                "https://piefed.social/c/playground",
                "https://hub.netzgemeinde.eu/followers/jupiter_rowland"
            ],
            "content": "<p></p>",
            "distinguished": false,
            "id": "https://hub.netzgemeinde.eu/item/73970039-849a-458e-b994-3014482fe0e9",
            "inReplyTo": "https://jolly-piefed.jomandoa.net/post/79247",
            "language": {
                "identifier": "en",
                "name": "English"
            },
            "mediaType": "text/html",
            "published": "2024-11-24T08:22:25.906356+00:00",
            "source": {
                "content": "",
                "mediaType": "text/markdown"
            },
            "to": [
                "https://www.w3.org/ns/activitystreams#Public",
                "https://jolly-piefed.jomandoa.net/u/jollyroberts"
            ],
            "type": "Note"
        }
    ],
    "sensitive": false,
    "source": {
        "content": "this is the poll post body",
        "mediaType": "text/markdown"
    },
    "stickied": false,
    "tag": [],
    "to": [
        "https://piefed.social/c/playground",
        "https://www.w3.org/ns/activitystreams#Public"
    ],
    "type": "Question",
    "votersCount": 2
}
```
