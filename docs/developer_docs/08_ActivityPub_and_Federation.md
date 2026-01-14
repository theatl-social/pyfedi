# PieFed and ActivityPub

It should not be any surprise if you have made it this deep into the documentation that PieFed uses the ActivityPub protocol to communicate with other instances across the Fediverse. Federation and ActivityPub is an integral part of how PieFed works and part of *the point* of PieFed. In fact, federation is a full 50% of the name PieFed!

ActivityPub can be a confusing bag of FEPs ([Fediverse Enhancement Proposals](https://codeberg.org/fediverse/fep)) with different software implementing some parts of the protocol and not others, or implementing custom extensions. The exact structure of the messages PieFed federates between servers is out of scope for this guide. Instead, let's look at the PieFed codebase and where incoming ActivityPub messages are parsed and where outgoing ActivityPub messages are built.

## Incoming ActivityPub Requests

PieFed, like Lemmy, uses a flavor of ActivityPub called [FEP-1b12](https://codeberg.org/fediverse/fep/src/branch/main/fep/1b12/fep-1b12.md) which focuses on federation centered around groups. In the PieFed context, a group is something like a community or a feed. This stands in contrast to something like Mastodon which focuses on federation of individual users.

ActivityPub messages between servers take the form of json payloads. The exact structure of these payloads is beyond the scope of this guide, but what it means is that when PieFed receives an ActivityPub message from another server, it needs to parse that json structure to figure how to process it and what actions to take. All of the ActivityPub messages are sent to the `/inbox` route. Like all the other requests that Flask handles, these requests are handled by a view function. This one is located in `app/activitypub/routes.py`. After some data cleaning and handling edge cases to make sure the data payload is in the right format, the view function ends with a call to `process_inbox_request`:

```python
@bp.route('/inbox', methods=['POST'])
def shared_inbox():

    # Lots of data cleaning and massaging goes here...

    process_inbox_request(request_json, store_ap_json)
```

The `process_inbox_request` function is where all the logic meant to parse ActivityPub json messages resides in PieFed. This guide is not meant and does not contain all the details of the ActivityPub spec. For some examples of what this json looks like, Mbin [provides a complete listing](https://docs.joinmbin.org/fediverse_developers/) of all the schema that program uses for federation and [lemmy's documentation provide](https://join-lemmy.org/docs/contributors/05-federation.html) some ActivityPub snippets.

If you are running your own PieFed instance, then it is possible to set an environment variable so that your instance will record all of the incoming ActivityPub messages it receives to the database so that you can inspect them. Set `LOG_ACTIVITYPUB_TO_DB='true'` to turn on this feature. This aids in debugging issues that might pop up when processing the incoming requests. By default, activities saved to the database in this way are purged after three days to prevent bloating the database.

## Outgoing ActivityPub Requests

Due to the network-bound nature of server to server communication, Outgoing federation within PieFed is handled asynchronously using celery tasks. That means that all of the outgoing ActivityPub code can be found in the `app/shared/tasks` folder broadly organized by the type of activity that is being sent.

One thing that is different in PieFed compared to some other fediverse software is the way in which activity sending can be batched. Some outgoing activities in PieFed are added to the database (the `ActivityBatch` model). Then, one of the recurring cron jobs set up during installation will process all of the pending activities in the database every 5 minutes. This allows for some activities to be grouped together to cut down the number of network requests that need to be made, helping everything run a bit more efficiently.

For example, a huge portion of the activities being federated are votes. PieFed will group all of the vote activities going to a particular instance between each execution of the send queue. That means one network request can federate out many votes instead of each vote being a separate network request. Additionally, the logic to handle these incoming activities need to be able to handle a collection of activities in a single json payload.

If you are running your own PieFed instance or are an admin on an instance, you can view all of the outgoing ActivityPub json that your instance is sending at `/admin/activities`. This allows you to inspect the structure of the json that is being sent to help debug any federation issues that you might be seeing when developing a new feature.
