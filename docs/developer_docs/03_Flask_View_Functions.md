# The PieFed Web UI - Working with Flask

PieFed is built using the [Flask framework](https://flask.palletsprojects.com/en/stable/). At a high level, when a user's browser visits a url, Flask executes different python functions depending on the path of the url. These functions are called [view functions](https://flask.palletsprojects.com/en/stable/tutorial/views/) in Flask parlance. This aim of this guide is to help developers new to the Flask framework understand how these view functions work and how PieFed has organized the url routing within the project.

## Minimum Viable View Function

In Flask, function decorators are used to map a url to a function. So, if we wanted a specific python function to execute whenever a user's browser requested the `/welcome` url path, we can specify that as part of the function decorator. Also, when a browser is just requesting a page, it is a `GET` request, so we also need to specify that the `GET` http method is allowed to call that function:

```python
@app.route('/welcome', methods=['GET'])
def welcome_view_function():
    ...
```

In general, any file in the codebase called `routes.py` is where these view functions are collected. There are many, many different possible urls that constitute a PieFed instance, so these view functions are divided across many `routes.py` files that are sorted into similar paths. For example, all of the `/admin/` routes have their corresponding view functions inside `app/admin/routes.py`. You will find other folders for different parts of the site (user, community, etc.). There are only a couple exceptions to this trend, but they relate to some special handling for activitypub requests and are beyond the scope of this guide's introduction.

These view functions can do a couple things after they are called. Some view functions return html to the browser to display, some will execute the function and then redirect the browser to a different page, others might kick off a background task before redirecting, etc. So, let's look at some of the more complex workflows that we can do with Flask view functions.

## Forms in Flask

Flask handles forms using a python library called [wtforms](https://wtforms.readthedocs.io/en/3.2.x/). This lets you define a web form as a python class and the different fields of the web form are attributes of that class. Similar to how all the view functions are grouped into `routes.py` files across different areas of the site, all the different web forms are grouped into multiple `forms.py` files. These forms are then instantiated inside a view function. So, if I was working on a view function in the admin portion of the site and needed to have a form, the view function might look like this:

```python
# First, import the form at the top of routes.py
from app.admin.forms import NewPageForm

# Need to now include the POST method, more on that later
@app.route('/admin/new_page', methods=['GET', 'POST'])
def new_page():
    # Instantiate the form
    form = NewPageForm()
```

You might have noticed that we now have two methods in our view function decorator. When the user clicks the submit button on a web form, the form data is submitted to that same url via a `POST` request (typically). So, for a url with forms, your view function now needs to support both the `GET` and `POST` http method and do different things depending on the method used. Forms in `wtforms` have a built in way to validate themselves if it is a `POST` request, so we can take advantage of that to organize our view function. Continuing the example from above, this kind of workflow happens a lot in PieFed's codebase:

```python
# First, import the form at the top of routes.py
from app.admin.forms import NewPageForm

# Need to now include the POST method, more on that later
@app.route('/admin/new_page', methods=['GET', 'POST'])
def new_page():
    # Instantiate the form
    form = NewPageForm()

    # Is this a POST request and is the data in the form valid?
    if form.validate_on_submit():
        # Yes! The form looks good. Do stuff with the form data here...

        # After you do what you need, either return html or redirect the browser
        return ...
    
    # Reaching this part of the code means that this is a GET request, not a form submission, return html for the browser
    return ...
```

The specifics on how to make forms in `wtforms` or how to make custom validation functions is beyond the scope of these docs. Feel free to reach out with any questions or issues you run into!

## Variables in Routes

For a site like PieFed, there are lots of unique urls (every post and comment can be a unique url for example), so writing a view function for every single url that can exist on a PieFed instance is just infeasible. What Flask does let us do is group many urls that look similar together into a single view function and then pass the part of the route that differs into the view function as a keyword variable.

The easiest way to understand this is to look at an example. Let's say we want to have a view function that displays a comment. However, every comment has a unique id and therefore has a unique url. So, let's make that comment id be a variable in the url, and have all comments share the same url structure, just with different id's. Our view funtion would look like this:

```python
# Note that we wrapped part of the url route in <> and gave it a type of int
@app.route('/comment/<int:comment_id>', methods=['GET'])
def show_comment(comment_id):
    # Note that the comment_id variable is now part of the function definition

    # We can use the comment_id variable inside our view function
    fetched_comment = PostReply.query.get(comment_id)

    ...
```

This view function is called whenever there is a url of the form `/comment/*`. The `int` part of the variable in the decorator means that Flask will try to coerce that part of the url into an int. If that coercion fails, then the browser will simply 404. There can be multiple variables of different types in the route that are specified this way (`/post/<int:post_id>/vote/<string:direction>` as an example)

## URL Parameters in View Functions

Some routes make use of [url parameters](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Query) which are treated differently in Flask. This is essentially a way to pass a dict of information to the view function through appending key-value pairs onto the end of the url. Take this url as an example:

```
https://piefed.social/communities?home_select=local
```

This is interpreted by flask to point to the view function for the `/communities` route but then there is this `?home_select=local` bit on the end. Flask passses this information to the view function as well. It can be accessed through the built-in Flask `request` object:

```python
@app.route('/communities', methods=['GET'])
def list_communities:
    # Access the url parameters by key through the request object
    # Best practice is to provide a fallback default value if the param is missing - 'any' in this case
    home_select = request.args.get('home_select', 'any')

    # For cases where multiple values for the same key are expected, use getlist()
    filters = request.args.getlist('filter', [])
```

In general, nothing sensitive should be handled as a url parameter (password, etc.). Also, url parameters are typically only used in `GET` requests to inform the server of how to tailor the response based on the provided parameters.

## Server Responses

Alright, so, once you understand how view functions are routed and how to pass data into a view function, what should the view function do when it is finished whatever it is doing? Well, that depends on the view function really...

For view functions corresponding to web interface routes, the answer is usually to return an html webpage to the browser that gets rendered for the end user. Many of the view functions you will come across in PieFed will end with returning a call to the `render_template` function. This is how a view function takes a jinja template and makes it into html that is sent to the browser. The details of this process can be found in the `Jinja` guide.

Another option is to redirect the browser to a different url (view function). This consists returning a call to the `redirect` function.

Routes that are part of the API typically return json to the client making the request. The structure of the json is specified in the api schema. The details of the API interface are found in the `API` guide.

Finally, there are also some routes that return different formats depending on details of the request. These routes are usually specific routes that can either serve html for a browser or json for an ActivityPub request from another instance/client for server-to-server communication. More details on ActivityPub can be found in the `ActivityPub` guide.


