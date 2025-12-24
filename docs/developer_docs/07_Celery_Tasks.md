# PieFed and Celery Tasks

Many things that a fediverse server needs to do doesn't necessarily need to happen immediately or results of the process might take some time to be accessible. For these kinds of things, PieFed tries to make use of a task queue framework called [Celery](https://docs.celeryq.dev/en/latest/index.html). By sending these kinds of tasks to celery, the server can run these in the background while not holding up everything else happening on the server.

## Sending a task to Celery

Not everything makes sense to be a task. Some things need to happen immediately as a reqeust is made such as fetching the contents of a post and sending it back to the client. However, for things that can safely happen in the backgroud, PieFed has separated all of the available celery task into the `app/shared/tasks` folder. Inside this folder, all of the tasks are listed in the `__init__.py` file.

So, how do we kick off a celery task from elsewhere in PieFed? To help with that, PieFed has the handy-dandy `task_selector`. As an example of how to send a task to celery, let's look at what happens when a user wants to subscribe to a community.

This process begins with the `app.shared.community.join_community` function. This function is basically just a way to kick off a celery task. The main thing that this function does is right here:

```python
sync_retval = task_selector('join_community', send_async, user_id=user_id, community_id=community_id, src=src)
```

The `task_selector` function let's you send a task to celery. In this case, we are telling celery to run the `join_community` task. The `send_async` argument is is a boolean that lets PieFed add a bit of a random delay to the beginning of the execution of the task. This is always `False` if a task is initiated in the web UI or if the site is in debug mode. However, outside of those cases, introducing the random delay actually helps prevent a bunch of scheduled tasks from all kicking off at the same time and overloading either your server or whatever server you might be making a bunch of requests to.

The other kwargs provided in the call to `task_selector` are the arguments passed through to the `join_community` task for celery to use. In this case, the `join_community` task is located at `app.shared.tasks.follows.join_community`. One thing to note is the arguments pass to `task_selector`, other than the task name and the async boolean, need to be keyword arguments. This lets them be passed through to the task properly.

## Writing a Celery Task

Because celery tasks run outside of the context of Flask, celery tasks need to be written a bit differently than a typical flask view function. The Database guide earlier in these guides already has information about this. To reiterate, the main thing to be wary of in celery tasks is that the database sessions need to be closed manually since flask is not managing the connection to the database to ensure it is closed properly. This means that most celery tasks have a structure similar to this:

```python
def my_cool_task(send_async, param1, param2):
    # First, use a helper function to connect to the database
    session = get_task_session()

    # Need to wrap database operations in a try except finally block
    try:
        # Do all the task logic things here
    except:
        # If there is a problem, rollback the database
        session.rollback()
        raise
    finally:
        # Close the session
        session.close()
```

Starting at the top of this, note that the task starts with the `send_async` parameter. This isn't really used by the tasks themselves, but it is used by the `task_selector` that initiates the tasks.

The next thing to note is that to connect to the database, you first need to create the session with the database with the helper function `get_task_session`. This does slightly change how you later execute queries. As a quick example to show the difference:

```python
# Executing query in flask context
user = User.query.filter(User.user_name == 'rimu').first()

# Executing query in celery task
user = session.query(User).filter(User.user_name == 'rimu').first()
```

All of the logic of the task is executed inside the `try` block. If there is an issue while running this, such as a database exception, then the code executes the `except` block. So, in here, we make sure to rollback any pending changes in the database. Then, the `finally` block is executed where we make sure to always close the database session.