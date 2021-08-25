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

    def __init__(self, mxid: str, profile: Any):
        super().__init__( mxid )
        self._profile = profile

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
        pass

    @property
    def email(self) -> str:
        pass

class MatrixRoom(MatrixIdentifier, backend.Room):
    """
    A matrix room
    """

    def __init__(self, mxid: str, client: nio.Client):
        super().__init__(mxid)
        self._client = client

        if mxid in self._client.rooms:
            self._room = self._client.rooms[ mxid ]
        else:
            self._room = None

    def join(self, username: str = None, password: str = None) -> None:
        if self._client:
            result = self._client.join( self._id )
            if isinstance(result, nio.responses.JoinError):
                raise backend.RoomError(result)

    def leave(self, reason: str = None) -> None:
        if self._client:
            result = self._client.room_leave(self.id)
            if isinstance(result, nio.responses.RoomLeaveError):
                raise backend.RoomError(result)

    def create(self) -> None:
        result = self._client.room_create()
        if isinstance(result, nio.responses.RoomCreateError):
            raise backend.RoomError(result)

    def destroy(self) -> None:
        result = self._client.room_forget(self._id)
        if isinstance(result, nio.RoomForgetError):
            raise backend.RoomError(result)

    @property
    def is_private(self) -> bool:
        native_room = self._client.rooms[ self._id ]
        return native_room.is_group and native_room.member_count == 2

    @property
    def exists(self) -> bool:
        all_rooms = set( self._client.rooms.keys() )
        return self._id in all_rooms

    @property
    def joined(self) -> bool:
        return self._room != None

    @property
    def topic(self) -> str:
        if not self.joined:
            raise backend.RoomNotJoinedError()
        return self._room.topic

    @topic.setter
    def topic(self, topic: str) -> None:
        pass

    @property
    def occupants(self) -> List[backend.RoomOccupant]:
        if not self.joined:
            raise backend.RoomNotJoinedError()

        people = list()
        for user in self._room.users:
            occupant = MatrixRoomOccupant( user.user_id, self._id, self._id )
            people.append( occupant )
        return people

    def invite(self, *args: List[Any]) -> None:
        for user_id in args:
            pass

class MatrixRoomOccupant(MatrixPerson, backend.RoomOccupant):
    """
    """

    def __init__(self, userid:str, profile: Any, channelid):
        super().__init__(userid, profile)
        self._room = channelid

    @property
    def room(self) -> Any:
        return self._room

class MatrixMessage(backend.Message):

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

    def clone(self):
        return MatrixMessage(
            body=self._body,
            frm=self._from,
            to=self._to,
            parent=self._parent,
            delayed=self._delayed,
            partial=self._partial,
            extras=self._extras,
            flow=self._flow,
        )

    @property
    def is_direct(self):
        return self.to.is_private

    @property
    def is_group(self):
        return not self.is_direct

    def __str__(self):
        return "BLARG"

class MatrixBackendAsync(object):
    """Async-native backend code"""

    def __init__(self, bot, client):
        self._bot = bot
        self._client = client
        self._md = xhtml()
        self._management = dict()

    def attach_callbacks(self):
        self._client.add_event_callback( self.on_message, nio.events.room_events.RoomMessageText )
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

    async def on_message(self, room, event: nio.events.room_events.RoomMessageText):
        """Callback for handling matrix messages"""

        try:
            log.info("got a message")
            err_room = MatrixRoom( room.room_id, self._client )
            msg = MatrixMessage(
                event.body,
                MatrixRoomOccupant( event.sender, self, room.room_id ),
                err_room
            )
            self._annotate_event( event, msg.extras )
            await self._bot.loop.run_in_executor(None, self._bot.callback_message, msg)
        except Exception as e:
            log.warning("something went wrong processing a message... %s", e)
            import traceback
            track = traceback.format_exc()
            print(track)

    async def on_invite(self, room, event: nio.events.invite_events.InviteEvent) -> None:
        """Callback for handling room invites"""
        await self._client.join( room.room_id )

    async def get_profile(self, user) -> dict:
        response = await self._client.get_profile( user )
        if isinstance(response, nio.responses.ProfileGetResponse):
            profile = {
                'name': response.displayname,
                'avatar': response.avatar_url,
                'extras': response.other_info
            }
            return profile
        else:
            return {}

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


    async def send_message(self, msg: backend.Message) -> None:
        """Send a errbot-style message to matrix"""

        log.info( "sending message to: %s", msg.to )
        try:
            target = msg.to
            if isinstance( target, str ):
                target = self._bot.build_identifier( target )

            if isinstance( target, MatrixPerson ):
                room_target = await self.get_private_channel( msg.to )
            else:
                room_target = target._id

            body = self._format( { 'msgtype': 'm.text', 'body': msg.body } )
            result = await self._client.room_send( 
                    room_id=room_target,
                    message_type='m.room.message',
                    content = body
                )

            if isinstance(result, nio.responses.RoomSendError):
                log.warning("message didn't send properly")
            log.debug(result)
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
            return MatrixPerson( txt, {} )
        elif txt[0] == '!':
            if txt in self._client.rooms:
                return MatrixRoom( txt, self._client )
        elif txt[0] == '#':
            for room in self._client.rooms.values():
                if room.canonical_alias == txt:
                    return MatrixRoom( txt, room )
        return None

    def build_reply(self,
            msg: backend.Message,
            text:str = None, private: bool = False, threaded: bool = False) -> backend.Message:
        log.info(f"Tried to build reply: {msg} - {text} - {private} - {threaded}")
        response = self.build_message(text)
        response.frm = self.bot_identifier
        response.to = msg.frm._room
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

