# Feeds as ActivityPub 'Group' Actors

Feeds are represented as ActivityPub Group Actors and can be Followed.


## Group objects as JSON

Server-to-server or server-to-client traffic that represents Feeds is sent as .json. I.e. when a remote server wishes to find out information about your local server's `technology` feed, the remote server will be sent that data in a json payload.


### Getting feed information

Piefed internally keeps track of feeds in a database, but you can query the information from the server as .json. There are many ways to do so, but here is an example using `curl`.

We will use the https://piefed.social flagship instance in the example. We will ask for information about the `linux` feed.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/f/linux
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "attributedTo": "https://piefed.social/f/linux/moderators",
    "endpoints": {
        "sharedInbox": "https://piefed.social/inbox"
    },
    "followers": "https://piefed.social/f/linux/followers",
    "following": "https://piefed.social/f/linux/following",
    "id": "https://piefed.social/f/linux",
    "inbox": "https://piefed.social/f/linux/inbox",
    "moderators": "https://piefed.social/f/linux/moderators",
    "name": "Linux & FOSS",
    "outbox": "https://piefed.social/f/linux/outbox",
    "preferredUsername": "linux",
    "publicKey": {
        "id": "https://piefed.social/f/linux#main-key",
        "owner": "https://piefed.social/f/linux",
        "publicKeyPem": "-----BEGIN PUBLIC KEY-----\+bXQcu5CClu6\nrQIDAQAB\n-----END PUBLIC KEY-----\n"
    },
    "published": "2025-03-02T17:15:36.886502+00:00",
    "sensitive": false,
    "type": "Feed",
    "updated": "2025-03-02T17:15:36.886506+00:00",
    "url": "https://piefed.social/f/linux"
}
```

NB the type is 'Feed', not 'Group' but for all intents and purposes it is a Group.

### Getting the communities in the feed

Now that we have the feed object we can retrieve the communities in the feed by requesting the url in it's `following` property


Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/f/linux/following
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "id": "https://piefed.social/f/linux/following",
    "items": [
        "https://rss.ponder.cat/c/9to5linux",
        "https://lemmy.ml/c/linuxhardware",
        "https://lemmy.ml/c/linux",
        "https://programming.dev/c/opensource",
        "https://lemmy.world/c/selfhosted",
        "https://lemmy.zip/c/linuxquestions",
        // etc etc
    ],
    "totalItems": 27,
    "type": "OrderedCollection"
}
```

The `orderedItems` list will be a list of community urls. When your local user subscribes to a Feed, send a follow and wait for the corresponding Accept activity to arrive.
Then find the list of communities in the feed (as above) and then send Follow activities to each of the communities on behalf of the user.

When a community is added or removed from a Feed, '[Add](https://codeberg.org/rimu/pyfedi/src/branch/main/docs/activitypub_examples/feeds/feed_add.json)'
or '[Remove](https://codeberg.org/rimu/pyfedi/src/branch/main/docs/activitypub_examples/feeds/feed_remove.json)' activities are sent to all followers.
You may wish to automatically join/leave communities when this happens.
