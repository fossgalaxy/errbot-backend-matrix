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

# markdown support
from markdown import Markdown

class ErrMatrixIdentifier(Identifier):
    pass

class ErrMatrixPerson(Person):

    def __init__(self, mxcid=None):
        self._mxcid = mxcid

    @property
    def person(self) -> str:
        return self._mxcid

    @property
    def client(self) -> str:
        return "" # TODO

    @property
    def nick(self) -> str:
        return self._mxcid

    @property
    def aclattr(self) -> str:
        return self._mxcid

    @property
    def fullname(self) -> str:
        return "Matrix User" # TODO

    def __str__(self):
        return self.nick

class ErrMatrixRoomOccupant(ErrMatrixPerson, RoomOccupant):

    def __init__(self, user_id, room_id, room=None):
        super().__init__(user_id)
        self._room = room_id
        self._roomObj = room

    @property
    def room(self) -> any:
        if not self._roomObj:
            return ErrMatrixRoom( self._room )
        else:
            return self._roomObj


class ErrMatrixRoom(ErrMatrixIdentifier, Room):
    def __init__(self, mxcid = None, lib_room=None, client=None):
        self._mxcid = mxcid
        self._room = lib_room
        self._client = client

    def join(self, username: str = None, password: str = None) -> None:
        pass

    def leave(self, reason: str = None) -> None:
        pass

    def create(self) -> None:
        pass

    def destory(self) -> None:
        pass

    def exists(self) -> bool:
        return False

    def joined(self) -> bool:
        return self._room != None

    @property
    def topic(self) -> str:
        if not self.joined():
            log.warn("tried to ask for topic for room we're not in")
            return None # contract error - mucnotjoinederror isn't a thing >.<

        return ""

    @topic.setter
    def topic(self, topic: str) -> None:
        pass

    @property
    def occupants(self) -> any:
        if not self.joined():
            log.warn("tried to ask for partipants for room we're not in")
            return None # contract error - mucnotjoinederror isn't a thing >.<
        
        people = list()
        for uid in self._room.users:
            people.append( ErrMatrixRoomOccupant(uid, self._mxcid, self ) )
        return people

    def invite(self, *args) -> None:
        for user in args:
            self._client.invite( self._mxcid, user )

    def __str__(self):
        if self._room:
            return self._room.display_name
        else:
            return self._mxcid


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

        self._md = Markdown()
        self._client = None
        self._ready = False

    def serve_once(self):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self._matrix_loop())

    def _format(self, msg):
        """Inject the HMTL version of a plain message"""
        if msg['msgtype'] == 'm.text' and 'format' not in msg:
            msg['format'] ='org.matrix.custom.html'
            msg['formatted_body'] = self._md.convert( msg['body'] )
        return msg

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

        # up to date, now things can happen
        self._client.add_event_callback( self.message_callback, RoomMessageText )
        self._client.add_event_callback( self._room_invite, events.invite_events.InviteEvent )

        self.identity = None
        self.connect_callback()

        log.debug("bot now in event loop - waiting on messages")
        await self._client.sync_forever(timeout=30000)

    async def message_callback(self, room, event) -> None:
        log.info(f"Got message from {room.room_id}: {event.body}")

        msg = Message(event.body)
        msg.frm = ErrMatrixRoomOccupant( event.sender, room.room_id )
        msg.to = ErrMatrixRoom( room.room_id )
        self.callback_message( msg )

    async def _room_invite(self, room, event) -> None:
        log.info(f"Got room invite {room} via {event.sender}")
        await self._client.join( room.room_id )

    def build_identifier(self, txt):
        pass

    def build_reply(self, msg, text=None, private=False, threaded=False):
        log.info(f"Tried to build reply: {msg} - {text} - {private} - {threaded}")
        response = self.build_message(text)
        response.to = msg.frm._room
        response.frm = self.identity
        return response

    def change_presence(self, status: str = '', message: str = ''):
        log.debug("presence change requested")
        pass

    def send_message(self, msg: Message):
        super().send_message(msg)
        asyncio.run_coroutine_threadsafe( self._mtx_send(msg), loop=self.loop )

    async def _mtx_send(self, msg: Message):
        log.debug("trying to send message to matrix")
        body = self._format( { 'msgtype': 'm.text', 'body': msg.body } )

        await self._client.room_send( 
                room_id=msg.to,
                message_type='m.room.message',
                content = body
            )
        log.debug("done")

    @property
    def mode(self):
        return 'matrix'

    def query_room(self, room: str):
        log.info( f"{self._client.rooms.keys()}" )

        if room not in self._client.rooms:
            raise RoomDoesNotExistError()
        return ErrMatrixRoom( room, self._client.rooms[room] )

    async def _mtx_rooms(self) -> list:
        resp = await self._client.joined_rooms()
        if isinstance(resp, responses.JoinedRoomsResponse):

            rooms = []
            for room_id in resp.rooms:
                mtx_room = self._client.rooms[room_id]

                # groups == 'DMs'
                if not mtx_room.is_group:
                    rooms.append( ErrMatrixRoom(room_id, mtx_room) )
            return rooms
        else:
            return []
        
    def rooms(self):
        future = asyncio.run_coroutine_threadsafe( self._mtx_rooms(), loop=self.loop )
        return future.result()
