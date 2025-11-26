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