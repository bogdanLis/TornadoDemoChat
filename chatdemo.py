#!/usr/bin/env python3
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import asyncio
import tornado.escape
import tornado.ioloop
import tornado.locks
import tornado.web
import os.path
import uuid
from pprint import pprint
try:
    from collections import MutableMapping #py2
except ImportError:
    from collections.abc import MutableMapping #py3
from tornado.options import define, options, parse_command_line
from pprint import pprint

global_session_dict = {}

define("port", default=8888, help="run on the given port", type=int)
define("debug", default=True, help="run in debug mode")


class MessageBuffer(object):
    def __init__(self):
        # cond is notified whenever the message cache is updated
        self.cond = tornado.locks.Condition()
        self.cache = []
        self.cache_size = 2000

    def get_messages_since(self, cursor):
        """Returns a list of messages newer than the given cursor.

        ``cursor`` should be the ``id`` of the last message received.
        """
        results = []
        for msg in reversed(self.cache):
            if msg["id"] == cursor:
                break
            results.append(msg)
        results.reverse()
        return results

    def add_message(self, message):
        self.cache.append(message)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]
        self.cond.notify_all()


# Making this a non-singleton is left as an exercise for the reader.
global_message_buffer = MessageBuffer()


class MainHandler(tornado.web.RequestHandler):

    def get(self):
        if not global_session_dict.get(self.get_secure_cookie('session')):
            self.redirect('/auth')
            return
        self.render("index.html", messages=global_message_buffer.cache)


class AuthHandler(tornado.web.RequestHandler):

    def get(self):
        self.render("auth.html", messages="")
    """Post a new message to the chat room."""
    def post(self):
        if not self.get_argument("pass") == "123":
            self.write("Лох, цветочник ебаный. Ты лох и кенты твои лохи")
        else:
            global_session_dict[self.get_secure_cookie('session')] = self.get_argument("name")
            self.write("заебись")


class MessageNewHandler(tornado.web.RequestHandler):
    """Post a new message to the chat room."""
    def post(self):
        sender = global_session_dict.get(self.get_secure_cookie('session'))
        if not sender:
            sender = self.get_argument("sender")
        message = {
            "id": str(uuid.uuid4()),
            "body": self.get_argument("body"),
            "sender": sender,
        }
        # render_string() returns a byte string, which is not supported
        # in json, so we must convert it to a character string.
        message["html"] = tornado.escape.to_unicode(
            self.render_string("message.html", message=message))
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        global_message_buffer.add_message(message)


class MessageUpdatesHandler(tornado.web.RequestHandler):
    """Long-polling request for new messages.

    Waits until new messages are available before returning anything.
    """
    async def post(self):
        cursor = self.get_argument("cursor", None)
        pprint(global_session_dict)
        messages = global_message_buffer.get_messages_since(cursor)
        while not messages:
            # Save the Future returned here so we can cancel it in
            # on_connection_close.
            self.wait_future = global_message_buffer.cond.wait()
            try:
                await self.wait_future
            except asyncio.CancelledError:
                return
            messages = global_message_buffer.get_messages_since(cursor)
        if self.request.connection.stream.closed():
            return
        self.write(dict(messages=messages))

    def on_connection_close(self):
        self.wait_future.cancel()

def main():
    parse_command_line()
    app = tornado.web.Application(
        [
            (r"/", MainHandler),
            (r"/auth", AuthHandler),
            (r"/a/message/new", MessageNewHandler),
            (r"/a/message/updates", MessageUpdatesHandler),
        ],
        cookie_secret="gefopkwrgipojkdlsmds3223okg2k90g32dfs",
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        xsrf_cookies=True,
        debug=options.debug,
    )
    app.listen(options.port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
