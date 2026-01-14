# PieFed's API Codebase

This guide is aimed at developers wanting to contribute to or better understand the PieFed API code inside the larger project. At a super high level, the API is handled no differently than the web UI; http requests are made to urls, Flask view functions execute, and finally a response is sent back. However, there are some important differences in the details, which this guide can hopefully help clarify.

## API View Functions

Similar to how the different parts of the web UI have their view functions sorted into different files called `routes.py`, the API also has its own `routes.py`. All of the API files are contained in the `app/api/alpha` folder, including the `routes.py` file. The OpenAPI specification (swagger) page for a piefed instance can be found by navigating to `/api/alpha/swagger` if the instance has enabled the api docs.

So, lets look at a view function for an API route. Specifically, let's look at `/api/alpha/community` with the `GET` method (the api routes are divided by http method, unlike how the web UI view functions typically work):

```python
@comm_bp.route("/community", methods=["GET"])
@comm_bp.doc(summary="Get / fetch a community.")
@comm_bp.arguments(GetCommunityRequest, location="query")
@comm_bp.response(200, GetCommunityResponse)
@comm_bp.alt_response(400, schema=DefaultError)
def get_alpha_community(data):
    if not enable_api():
        return abort(400, message="alpha api is not enabled")
    auth = request.headers.get('Authorization')
    resp = get_community(auth, data)
    return GetCommunityResponse().load(resp)
```

The first thing that is obviously different about this view function is all the decorators on the function. The API routes make use of the [flask-smorest](https://flask-smorest.readthedocs.io/en/latest/) python library to automatically document the OpenAPI spec and these decorators are part of how that is done. You might notice that the decorators all start with `comm_bp` and other decorators for other API routes are things like `post_bp` or `user_bp`. These different decorators help organize the resulting API spec so that related endpoints are grouped together so that it is easier to understand (comm for community endpoints, user for user endpoints, etc.).

Moving down the list of decorators, the next one, `@comm_bp.doc`, is how we can provide a concise summary of the purpose of that API endpoint that is displayed on the swagger page before the details of the endpoint are expanded.

The next two decorators, `arguments` and `response`, are closely related to schema, so look for more details on those in the schema section of this guide. Basically, the `arguments` decorator points to a structure that specifies what data is needed for that endpoint, how that data should be structured, and how that data is passed to the view function. The `response` decorator similarly points to a structure that specifies what data the endpoint will respond with and how it is structured.

To wrap up the decorators, the `alt_response` decorator is how we can signal what other types of responses the API can return. Typically, this is the response that is returned if there is an exception during execution or a problem with the request (thus the 400 response code).

One thing to notice about the view function is that it takes a parameter called `data`. This is standard for any route for which there is a corresponding `arguments` decorator and data is expected. Also note that every endpoint starts by checking to make sure the API is enabled, and returning an error if it is not. Finally, auth'd requests all expect a header with the bearer token in it and the auth workflow is standardized across the API in this way.

## Argument and Response Schema

In the previous section, I mentioned schema a lot, but how are they defined and used? Fittingly, all of the schema used by the api is defined in `schema.py`. All of the schematization of the API is done with a python library called [marshmallow](https://marshmallow.readthedocs.io/en/latest/).

### Defining a Schema

Each schema is represented as a `class` in the `schema.py` file with the attributes of that class being the different keys in the dict that defines the structure of the data. So, looking at the `GET /api/alpha/community` endpoint from earlier, we saw that it had a decorator that looked like this:

```python
@comm_bp.arguments(GetCommunityRequest, location="query")
```

This is referencing the `GetCommunityRequest` class that is defined in `schema.py`. The location argument means that this data should be provided as url parameters rather than as a request body. If we look at the corresponding class in the schema file, we see:

```python
class GetCommunityRequest(DefaultSchema):
    id = fields.Integer()
    name = fields.String()
```

This means that there are two possible keys with data that this endpoint expects: `id` and/or `name`. Both of these attributes of the class are defined as types of `fields`. This defines the type of data that is expected for the data in that field. A list of possible field types can be found in the [marshmallow docs](https://marshmallow.readthedocs.io/en/latest/marshmallow.fields.html#module-marshmallow.fields). One note about the field types is that, in general, the `fields.Url` type is often too strict with its validation to cover all the urls that are present across the fediverse. It is usually best to use `fields.String` and then hint that it should be formatted as a url. There are many examples of this already in `schema.py`, but format hinting can be done using the `metadata` kwarg provided to the field. Let's look more at how to customize a field in a schema.

### Documenting a Schema

Ultimately, one of the goals of this schematization is that we can have a parseable and predictable input and output of our API. That means that we want to document it well so that both humans and other programs understand it. To that end, there are many different things we can do with fields in the schema to provide more information about what the data in that field should look like. Let's look at an example to start:

```python
icon_url = fields.String(required=True, allow_none=True, metadata={"description": "This is a url pointing to the icon", "format": "url", "example": "https://piefed.social/static/media/logo_zI2kw_152.png"})
```

This shows many of the other things that can be provided inside the field when defining the schema. The `required=True` means that this field must always be present for this schema to be valid. By default, marshmallow does not consider a value of `null` or `None` to be valid for a field. So, the `allow_none=True` argument allows those null values to be valid in the schema. Finally, the `metadata` argument is a dict with supplemental information for the documentation. In the example above, we have provided a short description of the field to aid in understanding, a hint at what the string formatting should look like, and finally an example of what a valid value would be. All of these are documented in the resulting OpenAPI specification.

Some fields have additional constraints in addition to just the type. An example might be a user's default sorting method for the comments on a post. There are only a couple valid options, so we can add a validator to the field when we define it:

```python
# Define list of options (near the top of schema.py)
default_comment_sorts_list = ["Hot", "Top", "New", "Old"]

class UserSaveSettingsRequest(DefaultSchema):
    default_comment_sort_type = fields.String(validate=validate.OneOf(default_comment_sorts_list))
```

This means that the value for this field must be one of the items in the list passed to the validate argument. There are many [different validators built into marshmallow](https://marshmallow.readthedocs.io/en/latest/marshmallow.validate.html) to choose from. These validators are also reflected in the OpenAPI spec where a field like the one above will be listed as an `enum` with the possible options available for it.

### Nesting Schema

Often in the API, we are building complex dict/json structures that are multiple levels deep and can include lists of structured objects. To do this in marshmallow, we need to nest schema inside one another. First, let's look at how you would define a field that is a list of integers:

```python
int_list = fields.List(fields.Integer(), metadata={"description": "A really cool list"})
```

Note that the `fields.List` takes another field as an argument. In the python code, this data structure would correspond to a key value of `int_list` which is a list of integers. Note that additional arguments for documentation are arguments on the `fields.List` rather than the field inside the list.

However, a list of numbers is pretty simple, how would we deal with more layers of complexity? That is where [nesting](https://marshmallow.readthedocs.io/en/latest/nesting.html) really comes to the fore. Let's say that instead of just having a list of integers, our list was a list of some other schema, how would we do that? First, we would need to define the schema that comprises our list, and then define another schema to stick it into, like so:

```python
class ListItem(DefaultSchema):
    field_1 = fields.Integer()
    field_2 = fields.String()

class ListItemList(DefaultSchema):
    my_list = fields.List(fields.Nested(ListItem), allow_none=True)
```

Notice that we have now specified that our first schema is nested inside our second, so that the list in the second schema is a list of items that all follow the first schema's structure. Nesting can also be done outside of a list to essentially nest a dict inside a dict. This is how you can quickly build up many layers of structure to the data. As an example of a schema with three layers:

```python
class InnermostLayer(DefaultSchema):
    inner_layer = fields.String()

class MiddleLayer(DefaultSchema):
    middle_layer = fields.Nested(InnermostLayer)

class OuterLayer(DefaultSchema):
    outer_layer = fields.Nested(MiddleLayer)
```

With this definition, if your `data` followed the `OuterLayer` schema, then to access the `inner_layer` value, you would do so the same way you access multiple layers of a dictionary in python: `answer = data['outer_layer']['middle_layer']['inner_layer']`.

All of this schematization means that the data passed to the API and the data coming from the API is organized like dictionaries (because it is actually being done in json, which is essentially the same data structure). So, when you are returning data from a view function, your data needs to be a dict that conforms to the schema specified in the `response` decorator. When you have this data, load it into the schema and return it from the view function:

```python
# Note the parentheses after the schema name, I forget those all the time and wonder why it isn't working
return MyCoolSchema().load(my_cool_dict)
```

Flask, marshmallow, and flask-smorest will do the rest and return the json to the API consumer from there.

## API Codebase Organization

As mentioned already, all the view functions for the api are organized into a single `routes.py` file and all the schema are organized into a single `schema.py` file. However, there are a couple other important places where the API code is kept. The first of these is the `app/api/alpha/utils` folder.

In `routes.py`, each flask view function calls a function inside one of the files contained within the `utils` folder. These files contain all the logic for fetching/modifying/saving the data that is required for the different endpoint operations.

When the endpoint's util function has completed, it needs to return data that is structured according to the response schema. All of the functions that format data in a schema-compatible way are located in `views.py`.

So, the flow of an API request goes something like this:

1. A user makes a request to an API endpoint, potentially providing a payload of data
2. The request is routed to the flask view function in `routes.py`
3. The decorator makes sure that data payload conforms to the arguments schema defined in `schema.py`
4. If the data payload is formatted correctly, the data is passed to the flask view function in `routes.py` as a parameter
5. The flask view function calls the corresponding function in the `utils` folder to actually execute the API endpoint's purpose
6. After completion, if return data is needed, the util function calls one or more functions in `views.py` to format the returned data
7. The formatted data is then returned to the flask view function in `routes.py`
8. This data is loaded into the response schema which validates that it conforms to the schema
9. The flask view function sends the properly formatted json back to the API client
