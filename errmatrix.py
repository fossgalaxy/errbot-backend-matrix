#! /usr/bin/env python3
##
# Errbot Matrix Backend
# Implemented for FOSS Galaxy, a bit hacked together but should work.
#
# This is based on the other backends that are out there for errbot.
##

import sys
import logging
import asyncio

from errbot.backends.base import (
    Person,
    Message,
    Room,
    RoomOccupant,
    RoomDoesNotExistError,
    Presence,
    Identifier
)
from errbot.core import ErrBot
from errbot.rendering import xhtml

log = logging.getLogger(__name__)

try:
    from nio import AsyncClient, events, responses, MatrixRoom, LoginResponse, RoomMessageText
except ImportError:
    log.exception("Could not import matrix backend")
    log.fatal(
            "You need to install the Matrix API in order to use the matrix backend"
            "You can do `pip install -r requirements.txt` to install it"
    )
    sys.exit(1)

class ErrMatrixIdentifier(Identifier):

    def __init__(self, mxid: str):
        self._id = mxid

    def __eq__(self, other):
        return self._id == other._id

    def __str__(self):
        return self._id

class ErrMatrixPerson(ErrMatrixIdentifier, Person):

    def __init__(self, mxid=None, profile=None):
        super().__init__( mxid )
        self._profile = profile

    @property
    def person(self) -> str:
        return self._id

    @property
    def client(self) -> str:
        return "" # TODO

    @property
    def nick(self) -> str:
        return self._id.split(":")[0][1:]

    @property
    def aclattr(self) -> str:
        return self._id

    @property
    def fullname(self) -> str:
        if self._profile:
            return self._profile.get('name', 'Matrix User')
        else:
            return "Matrix User"

    def __str__(self):
        return self.nick

class ErrMatrixRoomOccupant(ErrMatrixIdentifier, Person, RoomOccupant):

    def __init__(self, user: ErrMatrixPerson, room_id, room=None, mxUser = None):
        super().__init__(user._id)
        self._user = user
        self._room = room_id
        self._roomObj = room
        self.mxUser = mxUser

    @property
    def person(self) -> str:
        return self._user.person

    @property
    def client(self) -> str:
        return self._user.client

    @property
    def nick(self) -> str:
        return self._user.nick

    @property
    def aclattr(self) -> str:
        return self._user.aclattr

    @property
    def fullname(self) -> str:
        if self.mxUser:
            return self.mxUser.name
        return self._user.fullname

    @property
    def room(self) -> any:
        if not self._roomObj:
            return ErrMatrixRoom( self._room )
        else:
            return self._roomObj

    def __str__(self):
        return self.fullname


class ErrMatrixRoom(ErrMatrixIdentifier, Room):
    def __init__(self, mxid: str = None, lib_room=None, client=None):
        super().__init__(mxid)
        self._room = lib_room
        self._client = client

    def join(self, username: str = None, password: str = None) -> None:
        # TODO handle async
        #self._client.room_leave( self.mxcid )
        pass

    def leave(self, reason: str = None) -> None:
        # TODO handle async
        #self._client.room_leave( self.mxcid )
        pass

    def create(self) -> None:
        pass

    def destory(self) -> None:
        pass

    def exists(self) -> bool:
        return self.joined()

    def joined(self) -> bool:
        return self._room != None

    @property
    def topic(self) -> str:
        if not self.joined():
            log.warn("tried to ask for topic for room we're not in")
            return "" # contract error - mucnotjoinederror isn't a thing >.<

        return self._room.topic

    @topic.setter
    def topic(self, topic: str) -> None:
        pass

    @property
    def occupants(self) -> any:
        if not self.joined():
            log.warn("tried to ask for partipants for room we're not in")
            return None # contract error - mucnotjoinederror isn't a thing >.<
        
        people = list()
        for user in self._room.users.values():
            profile = {
                'name': user.display_name,
                'avatar': user.avatar_url,
                'user': user
            }
            sender = ErrMatrixPerson( user.user_id, profile )
            people.append( ErrMatrixRoomOccupant( sender, self._id, self ) )
        return people

    def invite(self, *args) -> None:
        for user in args:
            self._client.invite( self._mxcid, user )

    def __str__(self):
        if self._room:
            return "{} ({})".format( self._room.display_name, self._room.machine_name )
        else:
            return self._id

class ErrMatrixPrivateRoom(ErrMatrixIdentifier, Person):
    """Repesentation of a user in a private room.
       
       This is a little nuts - in Matrix it's really a room, but we
       hide this from the bot and tell it that it's a person to stop
       it yelling at us"""

    def __init__(self, user: ErrMatrixPerson, room: ErrMatrixRoom):
        super().__init__(room._id)
        self._user = user
        self._roomObj = room

    @property
    def person(self) -> str:
        return self._user.person

    @property
    def client(self) -> str:
        return self._user.client

    @property
    def nick(self) -> str:
        return self._user.nick

    @property
    def aclattr(self) -> str:
        return self._user.aclattr

    @property
    def fullname(self) -> str:
        return str(self._roomObj)

    def __str__(self) -> str:
        return self.fullname


class MatrixBackendAsync(object):
    """Async-native backend code"""

    def __init__(self, bot, client):
        self._bot = bot
        self._client = client
        self._md = xhtml()

        # register callbacks
        self._client.add_event_callback( self.on_message, events.room_events.RoomMessageText )
        self._client.add_event_callback( self.on_invite, events.invite_events.InviteEvent )

    def _format(self, msg):
        """Inject the HMTL version of a plain message"""
        if msg['msgtype'] == 'm.text' and 'format' not in msg:
            msg['format'] ='org.matrix.custom.html'
            msg['formatted_body'] = self._md.convert( msg['body'] )
        return msg

    def _annotate_event(self, event: events.room_events.Event, extras: dict):
        extras['event_id'] = event.event_id
        extras['sender'] = event.sender
        extras['timestamp'] = event.server_timestamp
        extras['decypted'] = event.decrypted
        extras['verified'] = event.verified

    async def on_message(self, room, event: events.room_events.RoomMessageText):
        """Callback for handling matrix messages"""

        log.info("got a message")

        msg = Message(event.body)

        # the room which the message was sent in
        err_room = ErrMatrixRoom( room.room_id, room, self._client )

        profile = await self.get_profile( event.sender )
        sender = ErrMatrixPerson( event.sender, profile )
        msg.frm = ErrMatrixRoomOccupant( sender, room.room_id )

        if room.is_group:
            # pretend a room is a person to fool errbot
            msg.to = ErrMatrixPrivateRoom( sender, err_room ) 
        else:
            msg.to = err_room

        self._annotate_event( event, msg.extras )
        self._bot.callback_message( msg )

    async def on_invite(self, room, event: events.invite_events.InviteEvent) -> None:
        """Callback for handling room invites"""
        await self._client.join( room.room_id )

    async def get_profile(self, user) -> dict:
        response = await self._client.get_profile( user )
        if isinstance(response, responses.ProfileGetResponse):
            profile = {
                'name': response.displayname,
                'avatar': response.avatar_url,
                'extras': response.other_info
            }
            return profile
        else:
            return {}

    async def send_message(self, msg: Message) -> None:
        """Send a errbot-style message to matrix"""
        body = self._format( { 'msgtype': 'm.text', 'body': msg.body } )
        await self._client.room_send( 
                room_id=msg.to,
                message_type='m.room.message',
                content = body
            )

class MatrixBackend(ErrBot):

    def __init__(self, config):
        super().__init__(config)

        identity = config.BOT_IDENTITY
        self.homeserver = identity['homeserver']
        self.user_id = identity['username']

        # for password-based login
        self.device = identity.get('device', None)
        self.password = identity.get('password', None)

        # for token-based login
        self.token = identity.get('token', None)
        self.device_id = identity.get('device_id', None)
        self.bot_identifier = ErrMatrixPerson(
            identity['username']
        ) # FIXME should be populated based on whoami

        self._client = None
        self._ready = False
        self._async = None

    def serve_once(self):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self._matrix_loop())

    async def _matrix_loop(self) -> None:
        log.info("Matrix main loop started")

        # fix homeserver address
        homeserver = self.homeserver
        if not homeserver.startswith("http://") and not homeserver.startswith("https://"):
            homeserver = "https://" + homeserver

        log.debug("Creating Matrix Client")
        self._client = AsyncClient(homeserver, self.user_id)

        if self.token:
            log.debug("Using token-based login")
            self._client.access_token = self.token
            self._client.device_id = self.device_id
        else:
            log.debug("Using password-based login")
            resp = await self._client.login( self.password, device_name = self.device )
            if (isinstance(resp, LoginResponse)):
                log.info("logged in using password, please use a token for production use!")
                log.info(f"in future, use - device_id: {resp.device_id} : token: {resp.access_token}")
                sys.exit(1)
            else:
                log.fatal(f"authentication failed, giving up! {resp}")

        # sync so we don't get the stuff from history
        await self._client.sync(30000)

        self._async = MatrixBackendAsync(self, self._client)
        self.identity = self._client.user_id

        log.debug("bot now in event loop - waiting on messages")
        self.connect_callback()
        await self._client.sync_forever(timeout=30000)

    def build_identifier(self, txt):
        if txt[0] == '@':
            future = asyncio.run_coroutine_threadsafe( self._async.get_profile(txt), loop=self.loop )
            return ErrMatrixPerson( txt, future.result() )
        elif txt[0] == '!':
            if txt in self._client.rooms:
                return ErrMatrixRoom( txt, self._client.rooms[txt] )
        elif txt[0] == '#':
            for room in self._client.rooms.values():
                if room.canonical_alias == txt:
                    return ErrMatrixRoom( txt, room )
        return None

    def build_reply(self, msg, text=None, private=False, threaded=False):
        log.info(f"Tried to build reply: {msg} - {text} - {private} - {threaded}")
        response = self.build_message(text)
        response.frm = self.identity

        response.to = msg.frm._room
        return response

    def change_presence(self, status: str = '', message: str = ''):
        log.debug("presence change requested")
        pass

    def send_message(self, msg: Message):
        super().send_message(msg)
        asyncio.run_coroutine_threadsafe( self._async.send_message(msg), loop=self.loop )

    @property
    def mode(self):
        return 'matrix'

    def is_from_self(self, msg: Message) -> bool:
        return msg.frm.person == self.identity

    def query_room(self, room: str):
        log.info( f"{self._client.rooms.keys()}" )
        return self.build_identifier( room )

    async def _mtx_rooms(self) -> list:
        resp = await self._client.joined_rooms()

        rooms = []
        if isinstance(resp, responses.JoinedRoomsResponse):
            for room_id in resp.rooms:
                mtx_room = self._client.rooms[room_id]
                if not mtx_room.is_group:
                    rooms.append( self.build_identifier(room_id) )

        return rooms
        
    def rooms(self):
        future = asyncio.run_coroutine_threadsafe( self._mtx_rooms(), loop=self.loop )
        return future.result()

