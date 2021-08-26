# Errbot Matrix Backend

*note:* This is currently a (functional) work in progress.

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

* Some missing features for backend API (room methods, user methods)
* Support for non-text message types (ie, images - limited support in place)
* Support for reactions (adding implemented, removing not implemented)

# Known issues

* Plugins that use images are unlikey to work - this is due to how matrix deals with images.
* !room join doesn't work, invite the bot to a room via matrix's invite process
* Although implemented, matrix chat effects don't seem to work.
* The bot defaults to 'text' rather than the more correct 'notice' for outgoing messages - it might not play nice with other bots.

# Setup Steps

The bot requires an exisitng account and access token. Once you have these setting up the bot is relatively
simple.

The configuration file for errbot looks like this:

```
backend = 'matrix'
bot_extra_backend_dir = r'./backends/' # path to backends folder

BOT_IDENTITY = {
    'homeserver': 'https://matrix.fgmx.uk',
    #'token': '' # ACCESS TOKEN HERE
}
```
