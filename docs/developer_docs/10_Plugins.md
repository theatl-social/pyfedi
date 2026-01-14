# PieFed Plugins

PieFed includes a basic plugin system to let instance administrators include some community developed features that are not part of the base software. The plugin system is pretty basic, however, seeing as these guides are notionally aimed at developers, this system might be of particular interest. So, let's talk about the plugin system, how it works, and how you might use it to make your own plugins for PieFed.

## Structure of a Plugin

There is a specific file structure that a plugin must have for PieFed to detect it and correctly load. Each plugin needs to exist as a folder inside the `/app/plugins` folder and contain its own `__init__.py` file:

```
app/
├─ plugins/
│  ├─ my_plugin/
│  │  ├─ __init__.py
```

Then, there are some required elements of the `__init__.py` file. Specifically, there must be a `plugin_info` function that returns some information about the plugin. This information is used to populate the list of loaded plugins on the instance admin dashboard. Looking at the example plugin included in the PieFed codebase gives you an idea of what this function should look like:

```python
def plugin_info():
    """Plugin metadata"""
    return {
        "name": "Example Plugin",
        "version": "1.0.0",
        "description": "A simple example plugin that demonstrates hook usage",
        "license": "AGPL-3.0",                      # Must be AGPL-compatible
        "source_url": "https://github.com/...",     # Required
        "author": "PieFed Team"
    }
```

The funtion should return a dictionary with the information about the plugin. Required fields used in the UI are `name` (this doesn't need to exactly match the folder name), `version`, `description`, and `source_url`. If this function and these fields are not present, then the plugin will not be loaded by PieFed and will not be displayed in the admin dashboard.

Outside of these required elements, plugins can take any form inside its folder. There can be multiple files, external libraries that are imported (these would need to be available in the environment, possibly requiring a modified `requirements.txt`), make network requests, etc. For ideas or examples of plugins, you can check out the [!piefed_plugins@piefed.social](https://piefed.social/c/piefed_plugins) community or just reach out directly.

## Executing Plugins

You can write all the plugin code you want, but there needs to be some way for that code to actually execute. The way that the PieFed plugin system does this is through the use of "hooks". These are spots in the code where specific actions are taking place, where PieFed will check to see if any plugins want to run when that event is occurring. The next section of this guide has more specifics about the hooks currently available in PieFed. For now, let's look at some of the finer points of how plugins are called, in what order, and how data is passed around.

In your plugin, you need to register your functions to execute when certain hooks are fired. This is done through the use of the `hook` function decorator. The easiest way to do this is to have the functions you intend on executing placed in your plugin's `__init__.py` file with the appropriate hooks. Looking at one of the functions in the example plugin in the codebase, we can see how this works:

```python
@hook("new_user")
def example_new_user(user):
    """Hook that runs after a new user is registered/created and verified"""
    if int(os.environ.get('FLASK_DEBUG', '0')):
        print(f"[PLUGIN DEBUG] New user is verified: {user.user_name}")
    return user
```

The first thing to notice here is the `hook` decorator where we specify that this is the function to run when the `new_user` hook is fired. In the simple example case like this, we don't do anything fancy with the `User` object passed in to the plugin except print some debugging code to the terminal.

There is nothing to prevent multiple plugins or functions from using the same hook. So, the plugin system needs some way to execute the multiple functions for each hook in a logical way. This is simply done by organizing all the functions registered for a specific hook in alphabetical order and then calling them sequentially one after the other. This means that you can have a predictable execution order if you know the names of the functions registered for a specific hook.

Something to note about multiple functions being registered for the same hook is that data can be modified and passed between sequential function calls. If we take a look at the `fire_hook` function that handles this, we see this basic structure (simplified and annotated for ease of understanding):

```python
def fire_hook(hook_name: str, data: Any = None, **kwargs) -> Any:
    # Sort functions registered to this hook alphabetically by function name
    sorted_handlers = sorted(_hooks[hook_name], key=lambda func: func.__name__)

    # Use data passed to the hook in our first function call
    result = data

    # Iterate through every function registered to the fired hook
    for handler in sorted_handlers:
        try:
            # Execute the function and save the returned data to be passed to the next function in the list
            result = handler(result, **kwargs)
        except Exception as e:
            # An exception in a plugin doesn't break anything, that plugin just gets skipped like nothing happened
            logger.error(f"Error in hook handler {handler.__name__}: {e}\n{traceback.format_exc()}")

    # Return the data after all functions execute back to where the hook was fired
    return result
```

We can see here that when data is passed when the hook is fired, that data is passed through to the first function registered to that hook. The returned data from that function is then passed as the input to the next function in the sequence, and so on. When the final function registered to that hook executes, the data that it returns is then returned back to the code wherever the hook was called from. Currently, no hooks make use of this returned data, but that could change in the future. Let's take a closer look at the hooks currently built into the PieFed codebase...

## Available Hooks to Trigger a Plugin

There are a number of hooks currently built into the system, and it is generally not too difficult to add more, so feel free to reach out with ideas for new hooks in the future. Let's take a look at the different hooks currently available.

### `cron_daily` Hook

This hook is run once each day when the dailiy maintenance task is executed by PieFed. It is run after all the maintenance tasks have been completed. If we look at where it is called in `app/cli.py`, then we can see that no data is passed to the plugin function and nothing should be returned from a plugin function using this hook:

```python
@app.cli.command('daily-maintenance-celery')
    def daily_maintenance_celery():
        """Schedule daily maintenance tasks via Celery background queue"""

        # Daily maintenance tasks execute first...

        plugins.fire_hook('cron_daily')
```

This hook would work well for a plugin that doesn't need to run too often or one that might take some time to complete its execution. It should not block the execution of anything else so long as it completes before the next attempted run of the daily maintenance task.

### `cron_often` Hook

This hook is run whenever PieFed processes the `SendQueue`. This is any federation activities that have been batched to be processed together, such as votes as well as do things like publish scheduled posts. By default, following the installation instructions, the `SendQueue` should run every five minutes. Similar to the `cron_daily` hook, this is called after all the `SendQueue` tasks have bee completed and does not pass data to the plugin, nor expect any data to be returned.

This hook would be good to use for any plugin that needs to run frequently and regularly, but probably not a plugin that is very computationally expensive. If the execution of the plugin bleeds into the next 5-minute cycle when the `SendQueue` is attempted to be run again, then that cycle will be skipped, waiting for the next 5 minute window to roll around.

### `new_user` Hook

This hook is called whenever a new user has been verified. This means that the new user has completed all of the registration steps including email verification and registration approval (if configured). This plugin passes the `User` object to the plugins, but does not expect any returned data from the plugin:

```python
def finalize_user_setup(user):

    # Doing some finalizing account stuff here...

    plugins.fire_hook("new_user", user)
```

For an example of a plugin making use of this hook, check out the [PieFed Onboarding](https://codeberg.org/wjs018/piefed_onboarding) plugin that allows for a newly verified user to receive a message, and have a set of default subscriptions as well as blocks.

### `new_registration_for_approval` Hook

This hook is executed whenever a user registers for the site (and registration is required). This hook passes the `UserRegistration` object to the plugin, but does not expect any data to be returned by the plugin. A plugin utilizing this hook would enable things like notifications to third party services to be sent with the application information, or for an automated application approval workflow to be developed.

### `before_post_create` Hook

This hook is run when a user is trying to create a post, but the post has not yet been created in the database nor federated out. Let's take a quick look at the post information that is passed to the plugin through this hook. From `app/communtiy/routes.py`:

```python
# Fire before_post_create hook for plugins
post_data = {
    'title': form.title.data,
    'content': form.body.data if hasattr(form, 'body') else '',
    'community': community.name,
    'community_id': community.id,
    'post_type': post_type,
    'user_id': current_user.id
}

plugins.fire_hook('before_post_create', post_data)
```

So, this is the information that is available to the plugin to act on. Note that no data is expected to be returned from plugins utilizing this hook. Also, this hook cannot actually modify this data before it is sent to the `make_post` function where the post is actually created. So, it is more useful as a way to be aware or notified if posts meet certain conditions. Examples might include if a post's body triggers an anti-LLM detection you have set up, or if the post's body or linked url contains language or point to a domain that triggers an automatic report for increased scrutiny.

### `after_post_create` Hook

This hook is run after a post has been fully created and (if applicable) federated out. Because the post has been fully created, this plugin is able to simply pass the `Post` object to the plugin. It doesn't expect any data to be returned. This hook might be useful for plugins looking to emulate an automoderator. If posts or post authors meet certain criteria, then they are automatically removed after creation, or a distinguished comment made in the post, etc. Note that if you intend to remove or edit posts after they have been created using this hook, then make sure to do so in a way that federates out instead of just simply editing the local database or else the rest of the fediverse will be out of step with the local instance.
