# PieFed JavaScript and CSS

In general, PieFed is pretty lean when it comes to JavaScript compared to most modern web development that make heavy use of JavaScript frameworks like React or Vue. As for CSS, PieFed makes use of [Sass](https://sass-lang.com/) to compile the css. This guide is intended to act as guide to how these tools are used within PieFed.

## Executing JavaScript and the CSP

The [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP) (CSP) is a way for a website to tell a browser how strict it should be in allowing JavaScript to execute in order to prevent malicious execution of outside code. For PieFed, the CSP is defined in `pyfedi.py`. With few exceptions, to allow JS to run in PieFed, you need to provide something called a [nonce](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/nonce). This is a string provided by the website to essentially prove that the JavaScript on the page is intended to be there and safe to run.

### Inline JavaScript

A nonce only needs to be provided when writing JS inside a `<script>` tag on a jinja template. The value of the nonce changes each network request, so to make our lives easier when editing jinja templates, the nonce is saved as a global variable within jinja. That means that anywhere in a jinja template, you can include the nonce as a python variable: `{{ nonce }}`. For a simple example of this, you can look at `post/post_edit.html`:

```jinja
<script nonce="{{ nonce }}">
    function ...
```

Sticking the nonce inside the `<script>` tag like this is the proper way to make sure that the browser will execute the JS inside the tag.

### External script file

The other way to include JS in PieFed is to write it in a separate file and then `src` it into the jinja template. All of the external JavaScript files for the project are saved inside the `app/static/js` folder. An example of how to execute JavaScript in this way can also be found in the `post/post_edit.html` template:

```jinja
<script src="/static/js/coolfieldset.js?v=3"></script>
```

Note that there is no nonce needed when doing this, however it is still best practice to do so. For example, in `base.html` you can find examples of providing the nonce when importing an external js file:

```jinja
<script type="text/javascript" src="{{ url_for('static', filename='js/htmx.min.js') }}" nonce="{{ nonce }}"></script>
<script type="text/javascript" src="{{ url_for('static', filename='js/user-mentions.js', changed=getmtime('js/user-mentions.js')) }}" nonce="{{ nonce }}"></script>
<script type="text/javascript" src="{{ url_for('static', filename='js/scripts.js', changed=getmtime('js/scripts.js')) }}" nonce="{{ nonce }}"></script>
```

An alternative way to bring in JavaScript written in an external file is to `include` it using jinja. An example of doing this can be found in `base.html`:

```jinja
<script type="text/javascript" nonce="{{ nonce }}">
    {% include "notifs.js" %}
</script>
```

Note that scripts included this way need to be in the `templates` folder just like any other jinja template.

## HTMX

An important part of the JavaScript landscape of PieFed is [htmx](https://htmx.org/). This means that it can be relatively easy to do simple interactivity on a page in a way that is easy to write in a jinja template (such as voting, which uses htmx). At a basic level, htmx uses html attributes to make network requests to the server and then swaps the returned html from the server back into the page. There are lots of great examples on the [htmx site](https://htmx.org/examples/), but let's look at a simple case in PieFed as well.

You might have noticed in various folders in `app/templates` that there are template files that start with a `_` character. This is a bit of a convention we have used to indicate that these templates are what we refer to as "partials", or, only a part of a page. This can either mean it is `include`d inside another jinja template or, more relevant for this guide, it is meant to be returned in response to an htmx request.

One of the simpler cases of htmx usage is in the bells that you can click to toggle on and off notifications for things like new posts by a user or in a community, etc. In PieFed parlance, these are referred to as Activity Alerts. Looking at `templates/user/show_profile.html` you can see where we `include` another template file that contains the code for the alert bell:

```jinja
{% if current_user.is_authenticated %}
    {% include 'user/_notification_toggle.html' %}
{% endif %}
```

Then, looking at the contents of that `include`d file, we can see the htmx attributes inside the `<a>` tag (formatted for readability):

```jinja
<a href="/user/{{ user.id }}/notification"
    rel="nofollow"
    aria-live="assertive"
    aria-label="{{ 'Notify about new posts by this person' if user.notify_new_posts(current_user.id) else 'Do not notify about new posts' }}"
    class="fe {{ 'fe-bell' if user.notify_new_posts(current_user.id) else 'fe-no-bell' }} no-underline"
    hx-post="/user/{{ user.id }}/notification"
    hx-trigger="click throttle:1s"
    hx-swap="outerHTML"
    title="{{ _('Notify about every new post by this person.') }}">
</a>
```

The attributes used by htmx in this partial are `hx-post`, `hx-trigger`, and `hx-swap`. The url specified by `hx-post` is where the request to the server is made (as a `POST` request). This needs to be handled by a Flask view function and return the partial html. The `hx-trigger` attribute specifies information about what causes the request/substitution to occur. In this case, it happens when the bell is clicked and can only happen at most once per second. Finally, the `hx-swap` attribute tells htmx where on the page to swap in the partial of html. In the case of `outerHTML`, it replaces itself with what is returned by the server. Note that, as seen in this example, the returned partials can also contain htmx themselves.

## Bootstrap

In the web UI, PieFed uses [Bootstrap](https://getbootstrap.com/docs/5.3/getting-started/introduction/) as its css framework. This provides a mature and well-documented base that can be used to style the site without needing to reinvent the metaphorical wheel. The Bootstrap docs are really good and it is widely used enough that information about it is pretty easily searchable. So, this section will be relatively short to try to explain a couple bits that can be a bit confusing if you haven't seen it before.

Bootstrap, like many other css frameworks, works primarily through assigning css classes to web elements so that they are styled or behave in specific ways. As an example, As an example, let's look at a piece of the sidebar when you are viewing your own user profile, pulled from `user/show_profile.html`:

```jinja
<div class="card mb-3">
    <div class="card-header">
        <h2>{{ _('Manage') }}</h2>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-4">
                <a class="w-100 btn btn-primary btn-sm" href="/u/{{ user.link() }}/profile">{{ _('Profile') }}</a>
            </div>
            <div class="col-4">
                <a class="w-100 btn btn-primary btn-sm" href="/user/settings">{{ _('Settings') }}</a>
            </div>
            <div class="col-4">
                <a class="w-100 btn btn-primary btn-sm" href="/user/files">{{ _('Files') }}</a>
            </div>
        </div>
    </div>
</div>
```

This code renders what Bootstrap calls a [card component](https://getbootstrap.com/docs/5.3/components/card/). Fittingly, the whole section is wrapped in a `<div>` with a css class of `card` and the different sections of the card are organized into `<div>`s of `card-header` and `card-body`. Other Bootstrap classes used in this include the`row` and `col-4` ([bootstrap columns](https://getbootstrap.com/docs/5.3/layout/columns/)) classes which defines the positioning and sizes of the elements using the css grid. There is the `w-100` class which expands an item to a width of 100% of its parent element. Finally there are the `btn`, `btn-primary`, and `btn-sm` classes which format the links in the `<a>` tags into [bootstrap buttons](https://getbootstrap.com/docs/5.3/components/buttons/) and provides some styling.

## Changing the CSS with SCSS

As mentioned at the top, PieFed makes use of Sass to compile the css that the project uses. All of the css and scss files are stored in the `app/static` folder with some files put into other folders within the static folder. I have tried to provide a brief overview of where to find the css that you might be looking for.

By using Sass and scss files, you should not, in general, be writing any css directly. Where possible, changes to css should be made to an scss file and then compile that into the relevant css file. After you have [installed Sass](https://sass-lang.com/install/), you can then do the compiling from the command line:

```bash
sass app/static/styles.scss app/static/styles.css
```

The `styles.scss` file contains the bulk of the css that you are likely to interested in changing or adding to. It is applied to every single page within PieFed because it is imported in `base.html`. If you are looking for a specific bit of css to tweak, this is the file to start your search.

There are a couple other css/scss files that might be of interest. First is `app/static/scss/_typography.scss`. This file defines many of the icons that appear in PieFed (things like the voting arrows, etc.). The font we use for these symbols is called Feather. In this scss file, we define the symbol from the feather font that should be displayed when we define a `<span>` with a specific css class. For example, if we wanted to add the three dot menu symbol somewhere in our jinja template, we could do so by including:

```jinja
<span class="fe fe-options"></span>
```

This span will then be replaced by the three dot menu symbol at runtime because of what is defined in `_typography.scss`. Specifically, in that file you can find this:

```css
.fe-options::before {
  content: "\e99b";
}
```

This places the symbol before the rest of the content of the span with class `.fe-options` - but there is no other content in the span, so we just end up with the symbol. You might be wondering how `\e99b` is translated to the three dot menu symbol though...

In the `static/fonts` folder, you can find folders for the different fonts in PieFed. Inside the `feather` folder, we have files that define all the glyphs in the font. You can load up the `feather.ttf` file into a site like [FontDrop](https://fontdrop.info) to take a look at all the different symbols in the font file. Hovering over a symbol tells you the designator for that symbol, and this is what needs to be defined in the `_typography.scss` file. This way, you can add or change the symbols from the feather font that are used in PieFed.

One final typography note is that the `_typography.scss` file is imported into `styles.scss`. So, recompiling the `styles.scss` file is the proper way to handle changes to the typography.
