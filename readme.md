# Errbot Matrix Backend

*note:* This is currently a (functional) work in progress.

## Features
* Get message from matrix (rooms, private messages)
* Send messages to matrix (responses) - with markdown support

### Still todo
Most (all) of these are in the library, just need mapping

* General code tidy up
* Some missing features for backend API (room methods, user methods)
* Support for e2e encryption (the matrix library natively supports it)
* Support for non-text message types (ie, images)
* Support for reactions

# Known issues

## Strange setup
The bot will exit if you use password authentication (after displaying the token and device id) - you then
need to manually stick these in the config file. Would be better if the bot could cache this in some errbot-y
way.

If the bot doesn't do this, the bot generates a new device on each connection, which quickly becomes madness
on the server-side (100s of devices when developing). By fixing the device ID and token, this doesn't happen.

The configuration file for errbot looks like this:

```
backend = 'matrix'
bot_extra_backend_dir = r'./backends/' # path to backends folder

BOT_IDENTITY = {
    'homeserver': 'https://matrix.fgmx.uk',
    'username': '@errbot:fossgalaxy.com',

    # set these to get the token and device id
    'password': '', # not used if token is set
    'device': '', # not used if token is set

    # once known...
    #'device_id': '', # DEVICE ID HERE
    #'token': '' # ACCESS TOKEN HERE
}
```
