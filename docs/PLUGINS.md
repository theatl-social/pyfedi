# Plugins

PieFed includes a simple plugin engine so third parties can extend PieFed functionality without adding their code to the
main PieFed project. All plugins run within PieFed and therefore must be licenced under an AGPL 3.0-compatible licence and their source code
publicly available.

Each plugin is a directory under app/plugins and must include a __init__.py file. In that file there must be a plugin_info()
function.

See app/plugins/example_plugin/* to get started. Also check out [!piefed_plugins@piefed.social](https://piefed.social/c/piefed_plugins) for more plugin discussion, ask questions, and browse examples.

Plugins can have their code executed by adding a @hook decorator to a function. The current list of hooks are:

 - `before_post_create` - as the name suggests, this is run before a post is created. The contents of the post is passed in through the parameters.
 Modify the data as you wish and `return` it.

  - `after_post_create` - take a guess.

  - `cron_often` - is run at a periodic interval. The frequency is determined by how often the send_queue runs. The cron hooks are executed from a CLI task and do not run in a request context.

  - `cron_daily` - is run once a day in the daily_maintenance_task.

  - `new_user` - is run when a new user is verified; meaning that they have completed any required email verification and their application has been accepted (if applicable). The newly created `User` object is passed to this hook as an argument. When this hook completes, it should return the `User` object again.

  - `new_registration_for_approval` - is run when a user has submitted an application and (if applicable) verified their email, but the application is awaiting admin approval. The `UserRegistration` object is passed to this plugin as an argument. When this hook completes, it should return the `UserRegistration` object again.

More hooks will be added over time, presently the plugin engine is still experimental and undergoing heavy development.
