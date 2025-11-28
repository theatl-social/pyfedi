# The PieFed Database

The metaphorical heart and soul of a PieFed instance is the PostgreSQL database that contains all of the data that the rest of the code saves data to and serves data from. The code interfaces with this database in one of two ways; either through the [sqlalchemy](https://www.sqlalchemy.org/) python library that acts as the [the ORM](https://en.wikipedia.org/wiki/Object%E2%80%93relational_mapping) for PieFed, or through manually written SQL statements (that are then executed via `sqlalchemy`).

This guide is meant to help developers understand some of the basic ways that database interactions are implemented in PieFed. It is not exhaustive of all the types of interactions or means by which to interact with the database. For help with more advanced workflows (joins, etc.), please feel free to reach out with questions!

## Using the ORM Workflow

The database schema are all defined in the [models.py file](https://codeberg.org/rimu/pyfedi/src/branch/main/app/models.py). The `sqlalchemy` structure (which they refer to as [declarative mapping](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#orm-declarative-mapping)) interprets each python `class` as an object that corresponds to a table in the database, and attributes of that class as columns in the corresponding table. All of this is meant to make it easy to query the database elsewhere in the codebase.

As an example, if I wanted to query how many posts a user with an `id` of 351 has made, then I can do it in a easily comprehensible  way with two lines of code using the ORM flow:

```python
# Fetch user with id=351, return object of class User
user_object = User.query.get(351)

# Return just the post_count column of the selected row in the table
num_posts = user_object.post_count
```

Similarly, values can be assigned/updated using this workflow as well. One caveat to this is that to actually save any updates/insertions to the database, we need to commit the updated/new values to the database. In most of the codebase, this can be done through the `db` object that is imported at the top of the file. Continuing the code from above, if I wanted to increment the post_count by 1, I could do it like this (making sure to commit the updated value back to the database):

```python
# Update the value of that column for the selected row in the table
user_object.post_count = num_posts + 1

# Use the db object to commit changes to the db from this session
db.session.commit()
```

Finally, to filter a table to a list of rows matching a criteria, the `filter` or `filter_by` functions can be used. So, if you wanted to get a list of all the posts that are in a specific community (with a `community_id` of 45) that have not been deleted and are not marked NSFW, you could do so like this:

```python
# using filter function - filter uses Boolean conditionals as arguments
post_list_1 = Post.query.filter(Post.community_id == 45, Post.deleted == False, Post.nsfw == False).all()

# using filter_by function - filter_by uses keyword arguments corresponding to column names
post_list_2 = Post.query.filter_by(community_id=45, deleted=False, nsfw=False).all()
```

## Executing Raw SQL

Using the sqlalchemy ORM workflow does make for easily readable and quick to write code. However, for queries that need a high level of performance or are difficult to translate into ORM function calls, raw SQL queries can also be executed. Executing queries in this way typically runs faster than querying the ORM models, but it can be more workload over time to make sure any raw queries are updated if that portion of the database changes its schema in some way.

As mentioned in the previous section, the ORM class names are translated to the different tables of the database. However, there is a subtlety that isn't obvious at first glance. Following python naming conventions in PEP 8, ORM classes in the `models.py` use the `CapWords` convention. As an example, the ORM class that corresponds to replies to posts uses a class name of `PostReply`. However, in the actual database, the table names use the `snake_case` convention. So, that `PostReply` ORM class corresponds to the `post_reply` table in the database. So, when writing raw SQL, make sure you are using these `snake_case` table names.

Raw SQL is still called and executed using sqlalchemy, but the query string is wrapped in the `text` function. Parameters can be specified using a dict argument after the query (for parameters prefixed withe a `:`). As an example, the following query fetches all the comments to a post (with a `post_id` of 95) that are not deleted:

```python
# The query is simply a string. Prefix variables with a : for substitution at execution time
query_string = 'SELECT id FROM "post_reply" WHERE post_id = :post_id AND deleted = :deleted'

# Wrap the query string in the text function, use a dict to substitute values
id_list = db.session.execute(text(query_string), {"post_id": 95, "deleted": False}).all()
```

## DB Interactions from Celery Tasks

When a database session is running inside Flask's web UI or from the API sections of the codebase, Flask will handle opening and closing the db session so that the number of connections to the database is pretty consistent over time. However, that is not the case when interacting with the database from celery tasks, outside of the Flask context. So, a special workflow needs to happen so that connections are reliably closed once the celery task completes execution and exits.

To properly manage database connections, a helper function exists to initially connect the celery task to a database session. Inside a celery task, a database session is opened using the `get_task_session()` function:

```python
from app.utils import get_task_session
session = get_task_session()
```

Then, to make sure that the database connection is properly closed whenever the celery task finishes execution (for any reason), the task needs to be wrapped in a `try` block with the `except` and `finally` parts defined using a structure like this:

```python
session = get_task_session()
try:
    # Implement task logic here
except:
    # A problem occurred, don't commit the database, instead rollback the changes
    session.rollback()
finally:
    # Ensure the session is always properly closed
    session.close()
```

## Changing the Database Schema

Sometimes a feature needs new data to be stored in the database. To do so, we need to add a place to store it, whether that be a new table in the database, or a new column on an existing table. In the world of databases, this is often called a migration. To handle migrations, `sqlalchemy` uses a tool called [alembic](https://alembic.sqlalchemy.org/en/latest/).

By using `alembic`, we can version the schema of the database in a similar manner to how the rest of the codebase is versioned with a tool like `git`. Much like `git` commits use hashes to uniquely identify them, each revision of the database schema and the code used to move between different versions is also assigned a unique has and a commit message.

An important note for developers is that if you are working on a feature that requires a database migration, it is best practice to engage in conversation with the maintainers earlier rather than later. `alembic` mandates that migrations happen in a specific, sequential order. So, if two developers both create different migrations from the same starting point, then only one of them can be accepted and the other must be fixed. So, reach out to us to help you integrate your migration easier as it will prevent developers stepping on each other's toes.

Now, let's walk through creating a database migration. Remember that our database schema is defined in the `models.py` file. So, let's add a boolean column to the `user` table. First, we need to add the attribute to the `User` class in the `models.py` file. In the file, we have already imported the `db` object from the flask app, so we just need to add a column to it that is part of the `User` class:

```python
class User(UserMixin, db.Model):
    ...
    is_cool = db.Column(db.Boolean, default=False)  # Mark whether the user is cool (or not)
    ...
```

When we save this file and start back up our instance...nothing happens. The column doesn't automatically show up in the database just from defining it in `models.py`, we need to tell flask that we have changed the database schema and go through the migration process. The details of the process are going to vary between docker and baremetal installs, but the commands listed out in the following steps need to be run in a terminal belonging to the same machine/environment or container as is running flask. For docker, that can mean needing to exec into a running container (the `app` container, not the `db` container) to run the commands.

Flask is smart enough to be able to analyze our new, updated `models.py` file and compare it against the current schema of the database. Then it can generate a script that will automatically apply the changes to the database needed to match the updated schema. So, the first step of this process is to tell flask that we changed the schema and want to create a migration to a new schema. Similar to a git commit, we also add a short message describing the change we are making. This can be done from the command line:

```bash
flask db migrate -m "Added a column to mark users as cool"
```

Running this command will generate our migration script and create a new python file in the `migrations/versions` folder. Importantly, creating the migration script like this does not actually execute the migration. This gives you a chance to inspect the generated script to make sure it is doing what you want. Also, you might need to add some additional code to the script to perform other actions such as calculating values to populate the column with at the time of creation.

After inspecting/customizing your migration script, make sure that it is added to git so that it is tracked. Then, when you are ready to execute the migration, we can do so from the command line:

```bash
flask db upgrade
```

The `upgrade` command executes all the migrations to bring your database up to the most recent schema. Similarly, you can use the `downgrade` command to undo a migration one at a time. The `current` command will output the hash of the migration that your database is currently running.