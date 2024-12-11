import asyncio
import json
import logging
import os
import threading
from difflib import get_close_matches

from telethon import TelegramClient, events, functions


class TelegramService:
    def __init__(self, msg_callback):
        self.logger = logging.getLogger('Telegram')
        self.logger.setLevel(logging.DEBUG)

        with open(os.environ.get('TELEGRAM_CREDENTIALS'), 'r') as f:
            tg_credentials = json.load(f)

        self.msg_callback = msg_callback
        self._contacts = {}

        self.thread = threading.Thread(
            target=self._thread,
            args=(tg_credentials['api_id'], tg_credentials['api_hash'])
        ) # Thread that handles telegram updates/events
        self.thread.start()

    async def incoming_msg_handler(self, event):
        u = await event.get_sender()
        contact_name = u.first_name + ((' ' + u.last_name) if u.last_name else '')

        self.logger.info(f"Received message from '{contact_name}': {event.raw_text}")

        self.msg_callback(contact_name, event.raw_text)

    def _thread(self, api_id, api_hash):
        self.logger.info('Started')

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = TelegramClient(
            os.environ.get('TELEGRAM_SESSION'),
            api_id, api_hash,
            loop=self.loop
        )

        with self.client:
            self.client.add_event_handler(
                self.incoming_msg_handler,
                events.NewMessage(incoming=True, func=lambda e: e.is_private) # Filter user chats (not groups, channels)
            )
            self._contacts = { # All contact names to lower case for easier name matching
                u.first_name.lower() + ((' ' + u.last_name.lower()) if u.last_name else ''): u.id
                for u in self.loop.run_until_complete(
                    self.client(functions.contacts.GetContactsRequest(hash=0))
                ).users
            }
            self.client.run_until_disconnected()
        self.loop.close()

    
    def send_message(self, name, message):
        # Warning: This method can only be called from a thread different than the one running the asyncio event loop
        
        contact_name = get_close_matches(word=name.lower(), possibilities=self._contacts.keys(), n=1)[0]
        user_id = self._contacts[contact_name]

        self.logger.info(f"Sending message to '{name}' [{contact_name}]: {message}")

        return asyncio.run_coroutine_threadsafe(
            self.client.send_message(user_id, message), self.loop
        ).result()

    def stop(self):
        # Warning: This method can only be called from a thread different than the one running the asyncio event loop

        disconnect_coro = self.client.disconnect()
        if disconnect_coro is not None:
            asyncio.run_coroutine_threadsafe(disconnect_coro, self.loop).result()
        self.thread.join()

        self.logger.info('Stopped')
