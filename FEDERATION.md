# Federation

## Supported federation protocols and standards

- [ActivityPub](https://www.w3.org/TR/activitypub/) (Server-to-Server)
- [WebFinger](https://webfinger.net/)
- [Http Signatures](https://datatracker.ietf.org/doc/html/draft-cavage-http-signatures)
- [NodeInfo](https://nodeinfo.diaspora.software/)

## Supported FEPS

- [FEP-67ff: FEDERATION.md](https://codeberg.org/fediverse/fep/src/branch/main/fep/67ff/fep-67ff.md)
- [FEP-f1d5: NodeInfo in Fediverse Software](https://codeberg.org/fediverse/fep/src/branch/main/fep/f1d5/fep-f1d5.md)
- [FEP-1b12: Group federation](https://codeberg.org/fediverse/fep/src/branch/main/fep/1b12/fep-1b12.md)
- [FEP-5feb: Search indexing consent for actors](https://codeberg.org/fediverse/fep/src/branch/main/fep/5feb/fep-5feb.md)
-[FEP-2677: Identifying the Application Actor](https://codeberg.org/fediverse/fep/src/branch/main/fep/2677/fep-2677.md)

## Partially Supported FEPS

- [FEP-c0e0: Emoji reactions](https://codeberg.org/fediverse/fep/src/branch/main/fep/c0e0/fep-c0e0.md)
  - Treated as a `like` or `upvote`
- [FEP-268d: Search consent signals for objects](https://codeberg.org/fediverse/fep/src/branch/main/fep/268d/fep-268d.md)
  - `"searchableBy": "https://www.w3.org/ns/activitystreams#Public"` == `"indexable": true`, any other content sets `"indexable": false`
  - `"searchableBy": ["https://alice.example/actor", "https://example.com/users/1/followers"]` is not currently supported.


## ActivityPub


## Additional documentation