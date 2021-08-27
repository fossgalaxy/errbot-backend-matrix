#! /usr/bin/env python3
##
# Errbot Matrix Backend
# Implemented for FOSS Galaxy, a bit hacked together but should work.
#
# This is based on the other backends that are out there for errbot.
##

import os
import sys
import logging
import asyncio

# image management
import mimetypes
from PIL import Image
import aiofiles.os

from dataclasses import dataclass
from typing import Any, Optional, List, Dict

import errbot.backends.base as backend
from errbot.core import ErrBot
from errbot.rendering import xhtml

log = logging.getLogger(__name__)

try:
    import nio
except ImportError:
    log.exception("Could not import matrix backend")
    log.fatal(
            "You need to install the Matrix API in order to use the matrix backend"
            "You can do `pip install -r requirements.txt` to install it"
    )
    sys.exit(1)

@dataclass
class MatrixProfile:
    full_name: str
    avatar_url: str
    extras: dict

    def emails(self) -> List[str]:
        if 'address' not in self.extras:
            return []
        else:
            return self.extras['address']

class MatrixIdentifier(backend.Identifier):

    def __init__(self, mxid: str):
        self._id = mxid

    def __eq__(self, other) -> bool:
        return self._id == other._id

    def __str__(self):
        return str(self._id)

class MatrixPerson(MatrixIdentifier):
    """
    A matrix user
    """

    def __init__(self, mxid: str, profile: MatrixProfile = None, client = None):
        super().__init__( mxid )
        self._client = client
        if profile:
            self._profile = profile
        else:
            self._profile = {}

    def real_user(self):
        """Return the current user.

        This exists to ensure that a plugin writer has an 'escape hatch' to avoid dealing with the
        occupant/user split. Calling this method on a `frm` will always get you the user object.
        """
        return self

    @property
    def person(self) -> str:
        return self._id

    @property
    def client(self) -> str:
        return ""

    @property
    def nick(self) -> str:
        return self._id.split(":")[0][1:]

    @property
    def aclattr(self) -> str:
        return self._id

    @property
    def fullname(self) -> str:
        return self._profile.full_name

    @property
    def email(self) -> str:
        emails = self._profile.emails()
        if not emails:
            return ""
        else:
            return emails[0]

class MatrixRoom(MatrixIdentifier, backend.Room):
    """ Representation of a matrix room.

    Provides a way to do room-related things. We need to be careful because this is one of the main places
    that the async and sync code mixes. 
    """

    def __init__(self, mxid: str, client: nio.Client):
        super().__init__(mxid)
        self._client = client

        if mxid in self._client.rooms:
            self._room = self._client.rooms[ mxid ]
        else:
            self._room = None

    def join(self, username: str = None, password: str = None) -> None:
        """Join a Matrix Room.

        username and password are defined in `Room` so we define them here as well, but they are ignored."""
        if not self._client or not self._id:
            raise backend.RoomError("No access to the client object, so can't join room!")

        result = self._client.join( self._id )
        if isinstance(result, nio.responses.JoinError):
            raise backend.RoomError(result)

    def leave(self, reason: str = None) -> None:
        if not self._client or not self._id:
            raise backend.RoomError("No access to the client object, so can't leave room!")

        result = self._client.room_leave(self._id)
        if isinstance( result, nio.responses.RoomLeaveError):
            raise backend.RoomError( result )

    def create(self) -> None:
        """Create a new room.

        If the room is created via this method, it's assumed to be a group room (because that was was errbot
        understood a room to be). Calling this on a room that has an ID will upset it."""
        if not self._client or self._id:
            raise Exception("no access to client, so cannot create room!")

        result = self._client.room_create()
        if isinstance(result, nio.responses.RoomCreateError):
            raise backend.RoomError(result)

    def destroy(self) -> None:
        """Destory a Room.

        In matrix, destroing a room isn't really a thing. We can forget a room, which is the same as parting.
        but a room will always exist as long as it has people in it. Calling this on a room without an ID
        will upset it."""
        if not self._client or not self._id:
            raise Exception("no access to client, so cannot forget room!")

        result = self._client.room_forget(self._id)
        if isinstance(result, nio.RoomForgetError):
            raise backend.RoomError(result)

    @property
    def is_private(self) -> bool:
        """Is this room private?

        We consider a room to be private if it contains exactly two people, and it marked as a 'group' room
        (as apposed to a public one)."""
        if not self._id or not self._client:
            return False

        log.debug("is a room: %s", self._room.is_group)
        log.debug("has a member count of : %s", self._room.member_count)
        return self._room.is_group and self._room.member_count == 2

    @property
    def exists(self) -> bool:
        """Does this room exist?"""
        if not self._id:
            return False

        all_rooms = set( self._client.rooms.keys() )
        return self._id in all_rooms

    @property
    def joined(self) -> bool:
        """Are we currently joined to this room?"""
        return self._room != None

    @property
    def topic(self) -> str:
        """Get the current topic this room.

        This will return an error if we're not in the room.
        """
        if not self.joined:
            raise backend.RoomNotJoinedError()
        return self._room.topic

    @topic.setter
    def topic(self, topic: str) -> None:
        """Update the topic for a room.

        We don't support this (yet)"""
        raise NotImplementedError("not supported yet")

    def get_occupant(self, mxid):
        """Get a matrix room occupant from an mxid"""
        if not self.joined:
            raise backend.RoomNotJoinedError()
        try:
            native_user = self._room.users[mxid]
            return MatrixRoomOccupant( native_user, self )
        except KeyError:
            return None

    @property
    def occupants(self) -> List[backend.RoomOccupant]:
        """Get RoomOccupant proxies for all room members."""
        if not self.joined:
            raise backend.RoomNotJoinedError()

        people = list()
        for user in self._room.users.values():
            people.append( MatrixRoomOccupant( user, self ) )
        return people

    def invite(self, *args: List[Any]) -> None:
        """Invite one or more users to a room.

        I'm just not tackling this one right now. I need to look into how it's actually used in the bot.
        """
        raise NotImplementedError("not supported")

    ##
    # Matrix Spesfic stuff
    ##

    @property
    def display_name(self):
        """Show the user friendly version of a room name."""
        if not self._room:
            return self._id
        return self._room.display_name

    @property
    def machine_name(self):
        """The room's machine name.

        This will either be the room id, or an alias."""
        if not self._room:
            return self._id
        return self._room.machine_name

    def powerlevel(self, user_id):
        """Return a matrix power level for a given user id.

        If we don't know, assume 0.
        """
        if not self._room:
            return 0

        if isinstance(user_id, MatrixPerson):
            user_id = user_id._id

        return self._room.powerlevels.users.get( user_id, 0 )

    def __str__(self):
        return "{} ({})".format( self.display_name, self.machine_name )

class MatrixRoomOccupant(backend.Person, backend.RoomOccupant):
    """
    Representation of a particular user in particular room.

    From a matrix perspective this isn't really a thing, but it *is* a thing in XMPP, which is probably why
    errbot makes the distinction. Just passing a Person object directly doesn't work because parts of the
    bot make use of the `room` method. This doens't inherit directly from MatrixPerson because we are
    checking on types in the backend to route messages in a way that errbot expects.
    """

    def __init__(self, native_occupant, channel: MatrixRoom):
        super().__init__()
        self._id = native_occupant.user_id
        self._native = native_occupant
        self._room = channel

    @property
    def person(self) -> str:
        try:
            return self._native.user_id
        except Exception as e:
            log.debug("what? %s", e)

    @property
    def client(self) -> str:
        """Get the client string.

        Matrix has device IDs, but i'm not sure they serve the same purpose as this (looks to be designed
        for resource support)."""
        return ""

    @property
    def nick(self) -> str:
        """Nick (shortname) of a user in a room.

        This delegates to the MatrixPerson object, which calculates the nick as @<nick>:example.com.

        Note, matrix supports per-room names and avatars. For now, I'm using their global one but we should
        probably support this on a per-room basis."""
        return self._native.user_id.split(":")[0][1:]

    @property
    def aclattr(self) -> str:
        """ACL name for RoomOccupant.

        I'm delegating to the mxid of the user. This could be something we could adapt so the acls aren't
        global (ie, @fred:example.com in #room:example.com != @fred:example.com in #room:example.net)."""
        return self._native.user_id

    @property
    def fullname(self) -> str:
        """Full name of a user in a room.

        Note, matrix supports per-room names and avatars. For now, I'm using their global one but we should
        probably support this on a per-room basis."""
        return self._native.name

    def real_room(self) -> MatrixRoom:
        """Return a reference to the Matrix Room Object.

        This allows 'easy' access to anything matrix-spesific on the room objects."""
        return self._room

    @property
    def room(self) -> MatrixRoom:
        """Return a representation of the room.

        Grepping the core, in most cases core simply call str(room) on this,
        but Flows *does* assume its a valid Identifer subclass"""
        return self._room

    @property
    def disambiguated_name(self):
        return self._native.disambiguated_name

    @property
    def powerlevel(self):
        return self._native.power_level

    @property
    def presence(self):
        return self._native.presence

    @property
    def currently_active(self):
        return self._native.currently_active

    @property
    def status_message(self):
        return self._native.status_msg

    def __str__(self):
        return "{} in {}".format( self.disambiguated_name, self._room )

MatrixMessageTypes = [
    # basic message
    "m.text",
    "m.notice",

    # rich messages
    "m.image",
    "m.audio",
    "m.video",
    "m.location",
    "m.emote"

    # room effects
    "nic.custom.confetti",
    "nic.custom.fireworks",
    "io.element.effect.snowfall",
    "io.element.effects.space_invaders"
]

class MatrixMessage(backend.Message):
    """A representation of a chat message.

    This is a matrix-spesific version of the generic message object. Mostly, it adds matrix-spesific concepts
    and 'fixes' the defintion of a private/public room to match matrix's expectations."""

    def __init__(self,
            body = "",
            frm = None,
            to = None,
            parent = None,
            delayed = False,
            partial = False,
            extras = None,
            flow = None):
        super().__init__(body, frm, to, parent, delayed, partial, extras, flow)
        self._msgtype = "m.text"
        self._content = dict()

    def clone(self):
        msg = MatrixMessage(
            body=self._body,
            frm=self._from,
            to=self._to,
            parent=self._parent,
            delayed=self._delayed,
            partial=self._partial,
            extras=self._extras,
            flow=self._flow,
        )
        msg._msgtype = self._msgtype
        msg._content = self._content
        return msg

    @property
    def event_id(self):
        """Get the Matrix Event ID.

        Only works for received events (as sent events won't have a messageID yet."""
        return self._extras.get('event_id', None)

    @property
    def msgtype(self):
        """Return the Matrix message type for this message"""
        return self._msgtype

    def get_custom(self, key):
        """Get custom content.

        Matrix messages could contain extra/useful fields in the body of the message. This exposes
        them for you."""
        return self._content.get(key, None)

    def set_custom(self, key, value):
        """Custom content keys.

        These will be merged with the matrix message before sending.
        Only use these if you know what you are doing!"""
        if value == None:
            del self._content[key]
        self._content[key] = value

    def set_msgtype(self, msg_type="m.text", idx=None):
        """Sets the message type.

        This will be used when sending the event to the matrix room.
        """
        # there is something strange with the special effect types...
        if idx:
            msg_type = MatrixMessageTypes[idx]

        if msg_type not in MatrixMessageTypes:
            log.warning("Unknown message type for matrix message: %s, known types are: %s", msg_type, MatrixMessageTypes)
        self._msgtype = msg_type

    @property
    def is_direct(self):
        """Is this a direct (non-group chat) message?

        In errbot, a direct message is from (frm) a Person, and to a Person. We represent this as from a
        person, and to a Room which meets our 'private' critera.

        In matrix, all chats are rooms and technically they can be made into group chats. There are room hints
        which state that a room is intended to be a direct message (but they're hints, not rules). We
        consider a direct message to be any message in a 'private' room (see MatrixRoom for what that means)"""
        return isinstance(self.frm, MatrixPerson) and self.to.is_private

    @property
    def is_group(self):
        """Is this a group (non-private) message?

        In errbot, a group message is between many partipants, and is from a RoomOccupant to a room object.
        We represent this as a MatrixRoomOccupant to a MatrixRoom.
        """
        return isinstance(self.frm, MatrixRoomOccupant) and not self.to.is_private

    def __str__(self):
        return "{}".format( self.body )

class MatrixBackendAsync(object):
    """Async-native backend code"""

    def __init__(self, bot, client):
        self._bot = bot
        self._client = client
        self._md = xhtml()
        self._management = dict()

    def attach_callbacks(self):
        self._client.add_event_callback( self.on_message, nio.events.room_events.RoomMessageText )
        self._client.add_event_callback( self.on_unknown, nio.events.room_events.UnknownEvent )
        self._client.add_event_callback( self.on_invite, nio.events.invite_events.InviteEvent )

    def _format(self, msg):
        """Inject the HMTL version of a plain message"""
        if msg['msgtype'] == 'm.text' and 'format' not in msg:
            msg['format'] ='org.matrix.custom.html'
            msg['formatted_body'] = self._md.convert( msg['body'] )
        return msg

    def _annotate_event(self, event: nio.events.room_events.Event, extras: dict):
        extras['event_id'] = event.event_id
        extras['sender'] = event.sender
        extras['timestamp'] = event.server_timestamp
        extras['decypted'] = event.decrypted
        extras['verified'] = event.verified

        # message type data
        if isinstance(event, nio.events.room_events.RoomMessage):
            source = event.flattened()
            log.debug("%s", source )

    async def on_message(self, room, event: nio.events.room_events.RoomMessageText):
        """Callback for handling matrix messages"""

        try:
            log.info("got a message")
            err_room = MatrixRoom( room.room_id, self._client )

            # because (presumably XMPP) the core bot plugins make assumptions about occupants
            if not err_room.is_private:
                err_sender = err_room.get_occupant( event.sender )
            else:
                err_sender = await self.get_matrix_person( event.sender )

            msg = MatrixMessage(
                event.body,
                err_sender,
                err_room
            )
            self._annotate_event( event, msg.extras )
            await self._bot.loop.run_in_executor(None, self._bot.callback_message, msg)
        except Exception as e:
            log.warning("something went wrong processing a message... %s", e)
            import traceback
            track = traceback.format_exc()
            print(track)

    async def on_unknown(self, room, event: nio.events.room_events.UnknownEvent):
        """Callback for unknown events"""

        if event.type == "m.reaction":
            return await self.on_reaction(room, event)
        else:
            log.debug( "unknown event: %s", event )

    async def on_reaction(self, room, event):
        """Handler for matrix reactions.

        This isn't offical yet, so rather than a 'real' callback I'm simulating it."""
        try:
            fields = event.source
            err_room = MatrixRoom( room.room_id, self._client )

            reactor = await self.get_matrix_person( fields['sender'] )
            if reactor == self._bot.bot_identifier:
                return

            action = backend.REACTION_ADDED
            timestamp = event.server_timestamp
            reaction_name = fields['content']['m.relates_to']['key']

            # find the original
            event2 = await self._client.room_get_event( room.room_id, fields['content']['m.relates_to']['event_id'] )
            if not isinstance(event2, nio.responses.RoomGetEventResponse):
                log.warning("got %s rather than RoomGetEventResponse", event2 )
                return

            reacted_to = { 'source': event2.event.source, 'room': err_room }
            reacted_to_owner = await self.get_matrix_person( event2.event.sender )

            reaction = backend.Reaction(
                    reactor,
                    reacted_to_owner,
                    action,
                    timestamp,
                    reaction_name,
                    reacted_to
            )
            await self._bot.loop.run_in_executor(None, self._bot.callback_reaction, reaction)
        except Exception as e:
            log.warning("something went wrong processing a reaction... %s", e)
            import traceback
            track = traceback.format_exc()
            print(track)


    async def on_invite(self, room, event: nio.events.invite_events.InviteEvent) -> None:
        """Callback for handling room invites"""
        await self._client.join( room.room_id )

    async def get_profile(self, user: str) -> dict:
        response = await self._client.get_profile( user )
        if isinstance(response, nio.responses.ProfileGetError):
            log.warning("error getting profile data for user: %s", response)
            return MatrixProfile()
        else:
            log.debug( "extra info %s is %s", user, response.other_info )
            return MatrixProfile( response.displayname, response.avatar_url, response.other_info )

    async def get_matrix_person(self, mxid: str) -> MatrixPerson:
        profile = await self.get_profile( mxid )
        return MatrixPerson( mxid, profile )

    async def get_private_channel(self, user):
        # FIXME this feels super hacky >.<

        # do we have a cached management room?
        if user._id in self._management:
            log.debug("had cached management room: %s", self._management[user._id])
            return self._management[user._id]

        # if not, we need to try and find a suitable one
        log.debug("no cached management room, long route")

        try:
            for (rid, room) in self._client.rooms.items():
                if not room.is_group or room.member_count != 2:
                    continue

                if user._id in room.users:
                    log.debug("found candidate management room, using that.")
                    self._management[user._id] = room.room_id
                    return room.room_id
        except Exception as e:
            log.debug("EXCEPTION DEEP IN ASYNC CODE! %s", e)

        # no suitable room? make one!
        log.debug("no suitable room, making new one!")
        new_room = await self._client.room_create(
                is_direct = True,
                invite = [ user._id ]
        )

        if isinstance(new_room, nio.responses.RoomCreateResponse):
            self._management[ user._id ] = new_room.room_id
            return new_room.room_id
        else:
            log.warning("could not create management room: %s", new_room)
            raise Exception("couldn't create management room")

    async def _get_room_id(self, msg):
        target = msg.to
        if isinstance( msg.to, str ):
            target = self._bot.build_identifier( target )

        if isinstance( target, MatrixPerson ):
            # sending to a person? find/create a management channel
            target = await self.get_private_channel( msg.to )
        else:
            # sending to a room? just do it directly
            target = target._id
            
        return target

    async def send_message(self, msg: backend.Message) -> None:
        """Send a errbot-style message to matrix"""

        log.debug( "sending message %s to: %s", msg, msg.to )

        try:
            # try to figure out where the message has to go...
            target = await self._get_room_id( msg )

            body = self._format( { 'msgtype': msg.msgtype, 'body': msg.body } )
            body.update( msg._content )

            result = await self._client.room_send( 
                    room_id = target,
                    message_type='m.room.message',
                    content = body
                )

            if isinstance(result, nio.responses.RoomSendError):
                log.warning("message didn't send properly")
        except Exception as e:
            import traceback
            track = traceback.format_exc()
            print(track)
            log.debug("error: %s", e)

    async def send_image(self, room, image):
        try:
            mime_type = mimetypes.guess_type( image )[0]
            if not mime_type.startswith("image/"):
                raise Exception("that was not an image!")

            im = Image.open(image)
            (width, height) = im.size

            # we need an mxc for the next step
            file_stat = await aiofiles.os.stat( image )
            async with aiofiles.open( image, "r+b") as f:
                resp, maybe_keys = await self._client.upload( f,
                        content_type=mime_type,
                        filename=os.path.basename( image ),
                        filesize = file_stat.st_size )
                if not isinstance(resp, nio.responses.UploadResponse):
                    log.debug("Error uploading image: %s", resp)
                    raise Exception("image didn't upload :(")

                content = {
                    "body": os.path.basename( image ),
                    "info": {
                        "size": file_stat.st_size,
                        "mimetype": mime_type,
                        "thumbnail_info": None,
                        "w": width,
                        "h": height,
                        "thumbnail_url": None
                    },
                    "msgtype": "m.image",
                    "url": resp.content_uri
                }

                try:
                    await self._client.room_send( room._id, message_type="m.room.message", content=content )
                except Exception as e:
                    log.debug("Error sending image, %s", e)
        except Exception as e:
            log.debug("Error sending image, %s", e)


    async def send_reaction(self, msg, reaction) -> None:
        """Try to send an MSC2677 reaction to a message.

        This isn't technically part of the spec, but it is in element, so should be displayed."""
        if not msg.event_id:
            raise Exception("cannot react to a message that wasn't sent from matrix!")

        try:
            target = await self._get_room_id( msg )
            return await self.annotate_event( target, msg.event_id, reaction )
        except Exception as e:
            import traceback
            track = traceback.format_exc()
            print(track)
            log.debug("error: %s", e)

    async def annotate_event(self, room_id, event_id, reaction) -> None:
        """Try to send an MSC2677 annotation to an event.

        This is a bit more risky that passing a message, because you can react to things that are not
        messages. I've created this because the event could be saved/supplied somehow and still be reactable.
        """
        try:
            body = { 'm.relates_to': {
                'rel_type': 'm.annotation',
                'event_id': event_id,
                'key': reaction
            }}
            result = await self._client.room_send(
                    room_id = room_id,
                    message_type = 'm.reaction',
                    content = body
                )
            if isinstance(result, nio.responses.RoomSendError):
                log.warning("reaction didn't send properly: %s", result)
        except Exception as e:
            import traceback
            track = traceback.format_exc()
            print(track)
            log.debug("error: %s", e)

    async def whoami(self) -> MatrixPerson:
        response = await self._client.whoami()
        if isinstance(response, nio.responses.WhoamiError):
            raise Exception("error calling whoami")

        self.user_id = response.user_id
        return await self.get_matrix_person( self.user_id )

class MatrixBackend(ErrBot):

    def __init__(self, config):
        super().__init__(config)

        self.homeserver = config.BOT_IDENTITY['homeserver']
        if not self.homeserver.startswith("http://") and not self.homeserver.startswith("https://"):
            self.homeserver = "https://" + self.homeserver

        self.token = config.BOT_IDENTITY['token']

        # for token-based login
        if not self.token:
            log.fatal("Bot didn't have a login token! - you need to give it one or it can't login!")
            sys.exit(1)

        # variables for matrix library
        self._client = None
        self._async = None

    def serve_once(self):
        self.loop = asyncio.get_event_loop()
        return self.loop.run_until_complete( self._matrix_loop() )

    async def _matrix_loop(self) -> bool:
        try:
            log.info("Matrix main loop started")

            if not self._client: 
                # login
                self._client = nio.AsyncClient(self.homeserver)
                self._client.access_token = self.token

                # setup async and call whoami
                self._async = MatrixBackendAsync(self, self._client)
                self.bot_identifier = await self._async.whoami()
                self._client.user = self.bot_identifier._id

                # sync so we don't get the stuff from history
                result = await self._client.sync(full_state=True)
                if isinstance(result, nio.responses.ErrorResponse):
                    raise ValueError(result)

                log.debug("bot now in event loop - waiting on messages")
                self._async.attach_callbacks()
                self.connect_callback()

            await self._client.sync_forever(timeout=150)
            return False
        except (KeyboardInterrupt, StopIteration):
            self.disconnect_callback()
            return True

    def build_identifier(self, txt: str):
        log.debug("getting identifier for: %s", txt) 
        if txt[0] == '@':
            person = MatrixPerson( txt, {} )
            person.stub = True
            return person
        elif txt[0] == '!':
            if txt in self._client.rooms:
                return MatrixRoom( txt, self._client )
        elif txt[0] == '#':
            for room in self._client.rooms.values():
                if room.canonical_alias == txt:
                    return MatrixRoom( room.room_id, self._client )
        return None

    def build_message(self, txt):
        return MatrixMessage(body=txt)

    def build_reply(self,
            msg: backend.Message,
            text:str = None, private: bool = False, threaded: bool = False) -> backend.Message:
        log.info(f"Tried to build reply: {msg} - {text} - {private} - {threaded}")

        response = self.build_message(text)
        response.frm = self.bot_identifier

        if private and not msg.to.is_private:
            # if it's private, and the room it's private, redirect to the user's management channel
            response.to = msg.frm._id
        else:
            response.to = msg.to
        return response

    def change_presence(self, status: str = '', message: str = ''):
        log.debug("presence change requested")
        pass

    def send_message(self, msg: backend.Message):
        super().send_message(msg)
        log.info("sending message...")
        future = asyncio.run_coroutine_threadsafe( self._async.send_message(msg), loop=self.loop )
        log.info("message submitted, result: %s", future.done)
#        return future.result()

    def send_image(self, room, image_path):
        future = asyncio.run_coroutine_threadsafe( self._async.send_image(room, image_path), loop=self.loop )


    def react(self, msg: backend.Message, reaction):
        """React to an existing message.

        msg is the message your reacting to, not your response!"""
        log.info("sending reaction...")
        asyncio.run_coroutine_threadsafe( self._async.send_reaction(msg, reaction), loop=self.loop )

    @property
    def mode(self):
        return 'matrix'

    def is_from_self(self, msg: backend.Message) -> bool:
        return msg.frm._id == self.bot_identifier._id

    def query_room(self, room: str):
        log.info( f"{self._client.rooms.keys()}" )
        return self.build_identifier( room )

    async def _mtx_rooms(self) -> list:
        resp = await self._client.joined_rooms()

        rooms = []
        if isinstance(resp, nio.responses.JoinedRoomsResponse):
            for room_id in resp.rooms:
                mtx_room = self._client.rooms[room_id]
                if not mtx_room.is_group:
                    rooms.append( self.build_identifier(room_id) )

        return rooms
        
    def rooms(self):
        future = asyncio.run_coroutine_threadsafe( self._mtx_rooms(), loop=self.loop )
        return future.result()

