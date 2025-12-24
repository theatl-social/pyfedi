# Local PieFed Development

You have made it this far through these guides and are interested in dipping your toes into PieFed development, but how do you get started? The easiest way to set up a local development environment is through Docker, and it can be a little bit different than the official installation instructions, so let's take a look at some of the tips and tricks for local development.

## Setting up the Environment

Overall, setting up a local instance is not that different than setting up an instance in production. So, you can mostly follow the standard docker install instructions. However, there are a couple things to help with local development where instructions will vary. So, I have tried to document those here.

First things first, we need to set up the environment variables that PieFed will be looking for when it is setting up its configuration. For a local environment, we are going to be making use of Flask's built-in development server. This helps us with a couple things. First, it will give us nice, interactable tracebacks directly in our browser whenever there is an exception thrown by python. Second, this dev server obviates the need for a reverse proxy like nginx. Finally, the dev server won't have any kind of caching, so we are always getting served fresh content as we update code on the back end.

The first environment variable we need to set is our server name. The dev server will be running on port 8030 of the localhost, so we can specify the local instance's server name like this in the `.env` file docker is using:

```
SERVER_NAME='127.0.0.1:8030'
```

Next, we need to actually tell Flask that we are in debug mode. This also does some things in the backend to make debugging a bit easier. For example, instead of introducing random delays to async tasks to help spread out network load, when in debug mode, tasks will just execute immediately so that you aren't waiting pointlessly for them. To set Flask into debug mode, add this to the `.env` file:

```
FLASK_DEBUG=1
```

One thing to note about local development is that not everything is going to work correctly. This is primarily down to many features requiring [TLS](https://developer.mozilla.org/en-US/docs/Glossary/TLS). So, features like federation, object storage, and properly displaying external images will not work correctly on a local-only install due network limitations. However, PieFed does ship with an environment variable to help in an environment without https. Include this in your `.env` file to ease local development in a http-only environment:

```
HTTP_PROTOCOL='http'
```

After going through the rest of the installation procedure (setting up directories, initializing the database, etc.), you are pretty much set up with a local instance. There is one main thing to do when developing that will make your life easier though, using the correct docker compose file and command. We have included a `compose.dev.yaml` file in the repository. This is an alternate compose file for running PieFed that has a couple features to make your development life easier. One of them is that it passes through the right flags to put Flask into development mode, as discussed above.

There are two other primary benefits of the dev compose file when it comes to local development that I want to highlight. The first of which is that it maps the local directory into the `web` docker container as a volume mount. So, when you build your docker containers from the root directory of the project folder, all of the files on your local filesystem are the same ones that the docker container sees, even if you edit them. This works well with Flask being in debug mode because it monitors the files in its project folder, and when it detects a change, it will reload and restart the dev server. Essentially, it means that you can do something like make changes to the codebase and those changes are automatically then incorporated into the local site being served (they are just a refresh away). You don't need to rebuild the docker container from scratch to incorporate the changed or added files to Flask.

The other primary benefit of the dev compose file is that it is set up to log directly to the terminal. This means that you can see things like network requests and even debugging `print` statements right in the terminal that you are running PieFed from. Just make sure to remove any stray debugging print statements before opening that pull request (be better than me in this regard).

Speaking about the terminal, let's talk about actually running your local instance using the dev compose file. When I am doing this, I find it easiest to devote a dedicated terminal window for the logging output that is running my docker stack. Then, I use other terminals as needed for things like git or exec'ing into containers. The docker command I use to build my local dev stack and then keep the window dedicated to the logging goes like this:

```bash
docker compose -f compose.dev.yaml up --build
```

The `-f` flag is what keeps that terminal window following the logging output of the docker containers. As mentioned before, it will also output any `print` statements coming from the backend.

## Additional Tools

In addition to the dev compose file, there is another tool built into the PieFed compose files to aid you on your development journey; Adminer. This is a docker service that runs alongside the other containers in the stack and lets you read and edit the postgres database directly in a browser. In an actual production environment, it would be best to either remove this service entirely from the compose file or not expose it through your reverse proxy. However, for development purposes, it is an incredibly helpful tool.

How to use Adminer and all of its capabilities is beyond the scope of this guide, but if you have followed this guide and the default dev compose file, then it should be available to you in a browser window at `http://127.0.0.1:8888`. To access the PieFed database, select PostgreSQL from the dropdown and enter the database credentials from your `.env` file and you should be able to log in. Along the left sidebar are all the different tables in the database, and clicking on `select` next to them, lets you view the data stored in that table. You can also execute raw SQL queries through the `SQL Command` link in the upper left.

If you are planning on working with the API, then it is convenient to have a tool that helps simplify making API requests and parsing the returned json messages. This isn't needed since you can always just use `curl` to do things like assign headers, select the correct http method, and send a properly formatted body with the request. However, I find it easier using an external tool. There are plenty of options out there for testing APIs in this way (Postman, etc.). One that I have used extensively and can be run entirely locally without an account tied to a cloud service is [HTTPie](https://httpie.io/). Plus, you get the benefit of using a program with pie in the name when testing PieFed. 🥧
