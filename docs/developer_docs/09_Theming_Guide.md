# PieFed Theming Guide

As mentioned earlier in these guides, PieFed makes use of the [Bootstrap](https://getbootstrap.com/docs/5.3/getting-started/introduction/) css framework for its styling. This means that to make a custom theme for the PieFed web interface, you are going to have to work alongside and/or overwrite Bootstrap css. Almost all of the current PieFed themes are more or less a custom css skin of the web UI. So, let's take a look at how to get started with making your own PieFed theme.

## File and Folder Naming Structure

A real quick side note about PieFed themes is that there is a required naming structure that is needed for your theme to be detected by the server. All of the theme files are saved as subfolders in `app/templates/themes`. The name of the directory your theme is stored in is important, and must match exactly the name of the json file inside of the folder containing your theme's information. Let's look at the file tree for the `Amethyst` theme as an example. Both the folder containing the theme and the json file within are named `amethyst` (case-sensitive).

```
app/
├─ templates/
│  ├─ themes/
│  │  ├─ amethyst/
│  │  │  ├─ amethyst.json
│  │  │  ├─ styles.css
```

Making sure that the folder and the json file have the same name is important to allow PieFed to navigate the directory stucture correctly to detect the theme. Inside this json file, we need to define at least a name for the theme. This name is what the PieFed UI will display to the user in the theme selection dropdown. Looking again at the `Amethyst` theme, we see that the json contains only this name definition:

```json
{
  "name": "Amethyst (anarchist.nexus)"
}
```

The final piece of the required theme puzzle is the `styles.css` file. This file, located in the theme's directory, is where PieFed will look to load the theme's default css. For most themes, this is where all or almost all of the actual work of theming takes place. This css file is the last stylesheet loaded in the `<head>` of the page with only the admin and user custom css coming afterwards. So, it lets you overwrite default css values coming from Bootstrap. So, let's take a look at how to customize the css for PieFed through your theme's `styles.css` file.

## The styles.css File

This file lets you overwrite the default css of PieFed. There are some things within Bootstrap that are `!important`, but with the load order mentioned above, you can overwrite them by specifying `!important` in your theme's css. Trying to include an entire crash course on css and the possibilities it unlocks is beyond the scope of this guide (and beyond the scope of your humbe author's abilities). So, to keep this manageable, here are some basics and examples of how it has been done for existing themes in the codebase.

Once again, let's look at the css file for the `Amethyst` theme as an example. Looking at the beginning of the file, we start with the `:root` pseudo-class:

```css
:root {
    --accent-color: #5900ff;
    --accent-color-hovered: #7f41f4;
    --accent-color-active: #b369ff;
    --accent-color-rgb: 151, 100, 255;
    --accent-color-hovered-rgb: 127, 65, 244;
    
    --bs-link-color: var(--accent-color);
    --bs-link-hover-color: var(--accent-color-hovered);
    --bs-link-color-rgb: var(--accent-color-rgb);
    --bs-link-hover-color-rgb: var(--accent-color-hovered-rgb);
}
```

The `:root` pseudo-class in css is a great place to define variables that end up getting used in several other areas of your theme. In this case, the Amethyst theme defines a bunch of colors to named variables, including overwriting the variables that are included with Bootstrap (the ones that start with `--bs-`).

Looking a bit further down the file, we can see how to handle differing styles for light and dark modes:

```css
[data-bs-theme="dark"] {
    color-scheme: dark;
    --bs-body-color: #adb5bd;
    --bs-body-color-rgb: 173, 181, 189;
    --bs-body-bg: #111111;
    --bs-body-bg-rgb: 33, 37, 41;
    ...
}
```

By specifying the `[data-bs-theme="dark"]` at the beginning, we are specifying these variables only take on the specified values when the site is in dark mode. Similarly, we could use `[data-bs-theme="light"]` to define the value of variables when the site is in light mode. These variables can then be used for the styles later in the file. As an example let's look at the style definition for the `<body>` tag:

```css
body {
    background-color: var(--bs-secondary-bg) !important;
}
```

This defines the overall background color for the page, and it uses the `--bs-secondary-bg` variable to do it. Additionally in this case, we have to use the `!important` designation to make sure we override this value from Bootstrap.

With these building blocks in place, the css-world is your oyster! There are two helpful tools I have found to identify css classes and experiment with modified css. The first of which is the built-in development tools of your browser (usually bound to F12). This lets you inspect elements to see what css classes might be assigned to them as well as what style rules are applied to those elements. You can even write a custom stylesheet inside your browser if you are so inclined. However, the other tool makes applying custom css as a test a bit easier; the Stylus browser extension. This extension allows you to define custom css files to use for different sites. This makes iterating css tweaks a lot easier than having your changes wiped out each time you refresh.

In general, we are very interested in supporting a variety of themes. So, feel free to reach out with ideas or suggestions to make your theming life easier. This can range from assigning a css class to certain elements, to including hidden elements that you can surface, or anything else you can think of.

## Advanced Theming

There are a couple ways that you can really take theming to a whole new level, but they require considerably more time and effort. So, consider yourself warned as you wade into the deep end.

### Custom JavaScript

There is one current theme in PieFed that makes use of some custom JavaScript; `HLT-Fruits`. There is not currently a standardized way to discover and include a JavaScript file as part of a theme. Instead, this has to be done on a case by case basis in the `<head>` of `base.html`. If we look at the relevant portion of `base.html` we can see:

```jinja
{% if current_user.is_authenticated and current_user.theme == 'hlt-fruits' -%}
    <script src="/static/themes/hlt-fruits/scripts.js" type="text/javascript" nonce="{{ nonce }}"></script>
{% endif -%}
```

So, if you wanted to include custom JavaScript as part of your theme, then you would need to modify `base.html` in a similar way for your theme. If you need help with this or if there is demand among other themers for a more standardized way to do this, then please reach out and get in touch with us for support.

### Custom Jinja Templates

If you have spent any time working on jinja templates within the PieFed codebase, you have probably noticed that almost all of them have some boilerplate code at the top of them:

```jinja
{% if theme() != 'piefed' and file_exists('app/templates/themes/' + theme() + '/base.html') -%}
    {% extends 'themes/' + theme() + '/base.html' -%}
{% else -%}
    {% extends "base.html" -%}
{% endif -%}
```

What this bit of code is doing is checking to see if there is a theme-specific jinja template for `base.html` that it should use instead of the default `base.html` template. This lets you completely rewrite what the base html structure of the site looks like. So, doing something like moving the sidebar to the left instead of the right, or making other changes to the layout become simpler as you can create a custom template for your theme.

In fact, the theming system of PieFed allows you to create a custom jinja template for any of the existing default templates. This is defined in `app/utils.py` in the `render_template` function. Taking a quick look at the relevant portion:

```python
def render_template(template_name: str, **context) -> Response:
    theme = current_theme()
    if theme != '' and os.path.exists(f'app/templates/themes/{theme}/{template_name}'):
        content = flask.render_template(f'themes/{theme}/{template_name}', **context)
    else:
        content = flask.render_template(template_name, **context)
```

So, anytime `render_template` is called in PieFed, it will first check for the template in the current theme's folder first. Then, if it doesn't exist there, it will use the default template. This essentially lets a theme completely rewrite the UI from the ground up if it so chooses. The only restriction would be that the jinja templates would still only have the information available to them that was passed into the `render_template` function.

The drawback of this incredible power to customize the site to your theme's will, is that the maintenance burden will be much higher. The PieFed project tends to move pretty quickly, and features are added or changed relatively often. A theme's custom templates would be outside the scope of our regular testing and troubleshooting in most cases. So, it would likely mean a higher support burden to maintain a large number of custom templates.