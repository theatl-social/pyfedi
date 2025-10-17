# Users as ActivityPub 'Person' Actors

Users on the fediverse are [Person](https://www.w3.org/TR/activitystreams-vocabulary/#dfn-person) actors.

## User objects as JSON

Server-to-server or server-to-client traffic that represents Users are sent as .json. I.e. when a remote server wishes to find out information about your user account on your local server, the remote server will be sent that data in a json payload.

### Getting user information

Piefed internally keeps track of users in a database, but you can query the information from the server as .json. There are many ways to do so, but here is an example using `curl`.

We will use the https://piefed.social flagship instance in the example. We will ask for information about the `rimu` user, PieFeds main developer.

Run this curl command:
```bash
curl -H 'Accept: application/activity+json' https://piefed.social/u/rimu
```

The result should look something like this:
```json
{
    "@context": [
        "https://www.w3.org/ns/activitystreams",
        "https://w3id.org/security/v1"
    ],
    "discoverable": true,
    "endpoints": {
        "sharedInbox": "https://piefed.social/inbox"
    },
    "icon": {
        "type": "Image",
        "url": "https://piefed.social/static/media/users/oW/FB/oWFBklQomqpBX52.jpg"
    },
    "id": "https://piefed.social/u/rimu",
    "inbox": "https://piefed.social/u/rimu/inbox",
    "indexable": true,
    "manuallyApprovesFollowers": false,
    "matrixUserId": "@rimuatkinson:matrix.org",
    "name": "Rimu",
    "outbox": "https://piefed.social/u/rimu/outbox",
    "preferredUsername": "rimu",
    "publicKey": {
        "id": "https://piefed.social/u/rimu#main-key",
        "owner": "https://piefed.social/u/rimu",
        "publicKeyPem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA165M8pQFvf7YY08Yt9pM\nC7CAf9nW/Xy16dk65pIsdKZ42Le1eQrJ6vEplbFdeO7WJkF89liSBnSnYhdfKCId\nGg1hD5rDjKNHgvNPNWHh2y4KXGgkZ2ry6uxk1h4iAu+zJbQ7l2gUHscalY1/wtOz\naRPGKdhN6A49VShjujTHBV3ZxieddC60AjF5m/CHeNg0PXCdfvdqniOp9m33+2bF\nEYnyV4IbreBg24tmmxWAjEaH0NntCh/5KhLz3YZcqQnrmC5QNNk5K1yeeEDMukOd\nK+tT0khsudgcfC26iBdzyKUNXkKOwSP1ivBSPEFxMKqJvL0BKhjtm8WjQMJhZVOM\nrwIDAQAB\n-----END PUBLIC KEY-----\n"
    },
    "published": "2024-01-04T03:12:32.116738+00:00",
    "source": {
        "content": "Developer of [PieFed](https://piefed.social), a sibling of Lemmy & Kbin.",
        "mediaType": "text/markdown"
    },
    "summary": "<p>Developer of <a href=\"https://piefed.social\" rel=\"nofollow ugc\" target=\"_blank\">PieFed</a>, a sibling of Lemmy &amp; Kbin.</p>\n",
    "type": "Person"
}
```
