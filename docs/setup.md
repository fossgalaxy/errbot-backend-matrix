# Matrix Backend Setup

## Setup steps
This is the 'standard' way Matrix bots tend to be setup. It's a little more involved than IRC, but still not
too bad.

### 1. Create an account for the Bot
Give it a strong password, you can create a strong password on the command line using something like this:
`pwgen -s 64 1`.

If you are using the (rather fantastic) `matrix-docker-ansible-deploy` this will make an account:

```
ansible-playbook -i inventory/hosts setup.yml --extra-vars='username=errbot password=PASSWORD_FOR_THE_BOT admin=no' --tags=register-user
```

Else, you can use the admin API, a client, or synapse-admin web interface.

### 2. Get an access token
If you give the bot an access token and server address, it can figure pretty much everything else out for
itself (device id, username, etc...).

You can do this using any HTTP client, for example curl:

```curl -X POST --header 'Content-Type: application/json' -d '{
    "identifier": { "type": "m.id.user", "user": "errbot" },
    "password": "PASSWORD_FOR_THE_BOT",
    "type": "m.login.password"
}' 'https://matrix.example.com/_matrix/client/r0/login'
```

### 3. Use the access token to connect
If you're using our docker image, set the environment varible in your docker-compose:

```
version: '3'

services:
  xmpp:
    image: "git.fossgalaxy.com:8042/irc/errbot/fg-errbot:matrix"
    environment:
      TZ: Europe/London"
      BOT_SERVER: 'https://matrix.example.com'
      BOT_TOKEN: '<token from step 2>'
      BOT_ADMINS: '@admin:example.com'
    volumes:
            - data:/home/errbot/bot/data
    restart: unless-stopped

volumes:
        data:
```

If you're not, setup your config.py, for example:

```
import logging

BACKEND = 'Matrix'
BASE_DIR = "/path/to/bot/dir/"

BOT_DATA_DIR = BASE_DIR + 'data/'
BOT_EXTRA_PLUGIN_DIR = BASE_DIR + 'plugins/'
BOT_EXTRA_BACKEND_DIR = BASE_DIR + 'backends/' # place where backend-matrix lives

BOT_LOG_FILE = BASE_DIR + r'errbot.log'
BOT_LOG_LEVEL = logging.DEBUG

BOT_ADMINS = ('@admin:example.com', )

BOT_IDENTITY = {
    'homeserver': 'https://matrix.example.com',
    'token': '<token from step 2>'
}
```

That's it, now just do the standard errbot stuff (install plugins, etc...)

If you are using matrix-registration and want errbot to manage registration tokens for you, check out our
matrix errbot plugin. 

## Acknowledgements
* Some steps adapted from [matrix-docker-ansible-deploy](https://github.com/spantaleev/matrix-docker-ansible-deploy/blob/master/docs/configuring-playbook-matrix-registration.md).

