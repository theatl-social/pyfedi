# Making html Using Jinja Templates

One of the return options available to a flask view function is to return html to the browser that creates the webpage for the route that was requested. However, how are we meant to build an entire, complex, web page from within a python view function? If you know anything about modern html, you know that there can be lots of boilerplate and a very deeply nested structure that is, overall, quite verbose. Are we really meant to save all of that html as a python string and return it? Fortunately, we can use the tools bundled with flask to make our lives easier.

One of the most powerful tools available to us is a templating language called [jinja](https://jinja.palletsprojects.com/en/stable/). At a high level, jinja allows us to write our webpage's html as a separate file that is then called from the view function and sent to the browser. The powerful part of this is that the jinja template can be passed information from the view function to customize how it is rendered. Inside the template, you can call other python functions, embed other jinja templates, construct `for` loops, use `if ... else ...` statements, and more.

All of this means that a jinja template file typically consists of some mix of a complete webpage (html, css, javascript), and python. When it is rendered by the view function, the python is executed, resulting in a complete web page sent to the browser. So, let's look at some of the features of jinja templates you will see within the PieFed codebase...

## Template Files Location and `base.html`

All of the jinja templates used by PieFed are stored in the `app/templates` folder. They are organized in subfolders in a similar way to the `routes.py` files depending on what part of the site they are a template for. If you are unsure what template file you should be looking at for a fix or feature, you can check what template is being called by looking at the view function for that route. The view function will likely have a line that looks something like this:

```python
return render_template('user/show_profile.html', ...)
```

This is calling the jinja template found at `app/templates/user/show_profile.html`. All of the data being passed to the template comes as arguments after the template file is specified. Let's peek at the top of this jinja file to see what it looks like:

```jinja
{% if theme() != 'piefed' and file_exists('app/templates/themes/' + theme() + '/base.html') -%}
    {% extends 'themes/' + theme() + '/base.html' -%}
{% else -%}
    {% extends "base.html" -%}
{% endif -%}
```

That doesn't look like html! In fact, in a jinja template, any section that is denoted by `{{  }}` is actually code that is meant to be executed when the template is rendered and sections denoted by `{%  %}` are control flow sections where stuff like `if` statement and `for` loops are specified. So, you can see that the very first line here is an `if` statement that is checking for theme-related templates. More about themes later in this series of guides. The part I wanted to focus on here is the `{% extends "base.html" -%}` part. Most jinja templates in the codebase are going to start with this near the top of the file, so what does it do and what is `base.html`?

The `extends` keyword in jinja means that the current template is actually meant to just be a part of a different template file. In our case, that means that the `show_profile.html` template is only meant to be a part of the template file `app/templates/base.html`. If you take a look at `base.html`, you will see that it contains lots of html boilerplate, like importing all of our css, our javascript, fonts, favicon, etc. Also contained in `base.html` are parts of the website that are always present, no matter what page you navigate to (navbar, footer, etc.). By having all our jinja templates extend from `base.html`, we can avoid having to rewrite all of this html for every template.

Looking just a little bit further down the jinja template for `show_profile.html` we see this line:

```jinja
{% block app_content %}
```

This is how we tell jinja where the content in the `show_profile.html` template fits inside the `base.html` template. The `block` that is named `app_content` inside the `base.html` template is replaced with the contents of the `show_profile.html` template.

One thing to note about this is that there can be multiple layers of templates. You can `render_template("template_1.html", ...)`, but then `template_1` can extend `template_2` file which in turn extends a `template_3` file. This structure allows for lots of reuse of templated html to save us having to write it all, but it can sometimes be confusing to follow the chain if you aren't familiar with it.

## Passing Data to Jinja Templates

As mentioned already, jinja templates are invoked through the `render_template` function. Using this, we can pass data to the jinja template that can be used in the jinja codeblocks. To help understand how we pass data to a jinja template and then use it, let's take a look at how we render the `/about` page for a PieFed instance.

The view function for the `/about` page is in the `app/main/routes.py` file. Taking a look at the call to the `render_template` function, we can see lots of keyword arguments provided to the function:

```python
return render_template('about.html', user_amount=user_amount, mau=MAU, posts_amount=posts_amount,
                       domains_amount=domains_amount, community_amount=community_amount, instance=instance,
                       admins=admins, staff=staff, cms_page=cms_page)
```

Each of these keyword arguments is passed to the jinja template as a variable that we can reference from the code portions of the template. Some of these variables are simple native data types like `int` while others are complete model objects that came from database queries. Let's take a look at the first paragraph (`<p>`) of the template to see how these variables can be used:

```jinja
<p> This site is a <a href="https://join.piefed.social/">PieFed</a> instance created on
    {{instance.created_at.strftime('%d-%m-%Y')}}. It is home to <a href="/people">{{user_amount}} users</a>
    (of which {{mau}} were active in the last month). In <a href="/communities?home_select=local"> {{community_amount}} communities</a>
    we discussed content from <a href="/domains">{{domains_amount}}</a> websites and made
    {{posts_amount}} posts.</p>
```

In the above paragraph, the first variable we reference, `instance`, is an object that was fetched from the database. So, we can access the `created_at` attribute directly, and then use the `datetime` builtin function `strftime` to format it as a string so that it is rendered in our paragraph correctly. Elsewhere in our paragraph, we are simply referencing variables that are `int`s. When referenced directly like this, they are coerced to `str` when rendered. If we try to refer to a variable that has not been passed to the template via `render_template`, then an exception is thrown and the page will not be rendered.

One thing to note is that the `g` variable within flask is special. It is an object that flask creates for each request that contains information about the request as well as some general information that PieFed automatically makes available with every request. In the `about.html` template, you can see that we make use of the `g` variable to access information about the site (site name, sidebar, etc.).

## Control Structures in Jinja

As mentioned before, jinja templates can have [control structures](https://jinja.palletsprojects.com/en/stable/templates/#list-of-control-structures) like `for` loops or `if` statements in them. These sections are enclosed in `{%  %}` and work similarly to their python equivalents, but there are a couple differences to make note of.

First of all, any control structure in jinja needs to both be opened and closed. Very basically, it means you need to do something along these lines:

```jinja
{% for item in iterable %}
    {% if item %}
        item is truthy!
    {% else %}
        item is not truthy!
    {% endif %}
{% endfor %}
```

So, each `for` needs a corresponding `endfor` and each `if` needs a corresponding `endif`.

Another difference with python loops is that jinja doesn't support a `break` keyword. So, once you start a loop, it will execute through every iteration and cannot be stopped early. So, make sure that you include logic on how to handle any potential form of data going through the loop and don't count on just stopping early.

Jinja does offer a couple helpers to make loops easier. Looking again at the `about.html` template, we can see an example of one in this line:

```jinja
<p>It is moderated by {% for s in staff %}<a href="/u/{{ s.user_name }}">{{ s.user_name }}</a>{{ ", " if not loop.last }}{% endfor %}.</p>
```

This lists all the staff members of the site separated by commas. However, when listing the last member of the list, we don't need a comma. So, we can use an `if` statement and the `loop.last` helper to exclude the comma for the final iteration of the for loop.

## Jinja Globals and Filters

Jinja includes several [builtin filters](https://jinja.palletsprojects.com/en/stable/templates/#list-of-builtin-filters) to make our lives easier. One of those can be seen in the `about.html` template; the `safe` filter:

```jinja
<p>{{ g.site.contact_email | safe }}</p>
```

This filter marks the string that results from this code execution as "safe". This means that jinja won't try to escape any special characters within the resulting string to make them html-safe.

There are also filters that we have written for use within the PieFed project. The custom filters are found in the `pyfed.py` file. Some example filters would include:

- `community_links` - automatically convert `!community@instance.tld` to a hyperlink
- `feed_links` - automatically convert `~feed@instance.tld` to a hyperlink
- `person_links` - automatically convert `@person@instance.tld` to a hyperlink
- `shorten` - truncates strings
- `shorten_url` - truncates urls

In addition to these custom filters that make PieFed specific tasks easier, we have also defined some global jinja functions. One of those you can see at the top of almost every template file, the `theme()` function. This is a function to check what theme the browser is currently using in case there is any special handling that needs to be done. More information on themes later in this series of guides. These global functions are similarly defined in the `pyfedi.py` file.

## Jinja Macros and Includes

Similar to how jinja has the `extends` keyword that embeds the called template inside of another, there is also the `include` keyword. This serves to embed another jinja template inside of another. As an example, if we look at the template `index.html` that is the PieFed homepage, we see several `include`s through the file.

```jinja
<div class="col-6 pe-1">
    {% include "_home_nav.html" %}
</div>
<div class="col-6 ps-1">
    {% include "_view_filter_nav.html" %}
</div>
```

This allows us to break apart giant template files into components. In the case above, these two `include` templates are for the navigation buttons along the top of the main content container of the page.

Another way to achieve a similar effect of including the contents of one template inside another is to make use of jinja macros. At a high level, using `include` and calling a macro achieve the same result. However, there can be some subtle differences that are not obvious. In the context of PieFed, macros can have a big benefit over many nested `include`d templates. So, if you find yourself dealing with more than a handful of nested jinja templates, consider making use of macros instead.

Macros within jinja function basically like a function. You define a macro in a template file, including the arguments that the macro requires. Then, you can import and invoke that macro from other template files. Looking at the `index.html` template again, we see this line near the top of the template:

```jinja
{% from "_macros.html" import render_communityname %}
```

This is similar to importing a python function from a module to use it in a script. In this case, this macro is used to render a community name on the page. Looking at the `_macros.html` file, we can see what arguments we need to provide to the macro when we call it from within the template:

```jinja
{% macro render_communityname(community, add_domain=True, low_bandwidth=False, collapsed=False) -%}
```

As you can see, this looks very much like defining a function in python, including default values for arguments. The only required argument here is the community object representing the community whose name is being rendered on the page. So, when we invoke this macro on `index.html`, we call it much like a python function:

```jinja
<li class="list-group-item">
    {{ render_communityname(community, low_bandwidth=low_bandwidth) }}
</li>
```

Whatever the macro returns is automatically substituted into this portion of the template, just as if we had `include`d a separate template file.
