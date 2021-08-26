# Errbot Matrix Backend

*note:* This is currently a (functional) work in progress.

Most development takes place on our gitlab server. We mirror to github because people have trouble finding
working errbot matrix backends, and well... ours kinda works :). PRs/issues/comments welcome.

## Features
* Single (1:1) rooms with the bot, which it considers private
* Group/named rooms
  * Room spesific full-names
  * Room aliases (#thing:example.com) are recognised and resolve correctly
* Sending of reactions to events
* Listening for reactions ([see the our errbot-matrix plugin](https://git.fossgalaxy.com/irc/errbot/errbot-matrix/-/blob/main/matrix.py))
* Notices, emotes, images - although the syntax requires a tidy up
* Exposing of matrix state (power levels, presence)
* Messages feature matrix spesific metadata in `extras` (event ids, times, etc...)
* Token-based auth, just like most native matrix bots :)
  * Name detection based on token

### Still todo
Most (all) of these are in the library, just need mapping

* Some missing features for backend API (invites, room methods)
* Support for non-text message types (ie, images - limited support in place)
* Support for redacting reactions (adding implemented, removing not implemented)
* Support for message editing/redactions

# Known issues

* Plugins that use images are unlikey to work - this is due to how matrix deals with images.
* !room join doesn't work, invite the bot to a room via matrix's invite process
* Although implemented, matrix chat effects don't seem to work.
* The bot defaults to 'text' rather than the more correct 'notice' for outgoing messages - it might not play nice with other bots.
* Careful when accessing async code, it works as-is, but can be a bit temprimental if you call async methods from sync ones.

# Setup Steps

The bot requires an exisitng account and access token. Once you have these setting up the bot is relatively
simple. The backend isn't currently on pypy, so you need to put it somewhere the bot can find it. We store
ours in a backends directory.

The configuration file for errbot looks like this:

```
backend = 'matrix'
bot_extra_backend_dir = r'./backends/' # path to backends folder

BOT_IDENTITY = {
    'homeserver': 'https://matrix.fgmx.uk',
    'token': 'MATRIX_ACCESS_TOKEN'
}
```

If you'd like to see a dockerised example, [fg-errbot's repo](https://git.fossgalaxy.com/irc/errbot/fg-errbot)
is our production setup, and it's FOSS. You can also find our collection of [errbot plugins](https://git.fossgalaxy.com/irc/errbot)
on our gitlab server.

If you'd like to see the matrix-spesific features exposed by the backend, ([see the our errbot-matrix plugin](https://git.fossgalaxy.com/irc/errbot/errbot-matrix/-/blob/main/matrix.py)).

## Thanks
This repository was inspired by existing err backends on github, namely the discord, slack and nio-matrix
backends.
