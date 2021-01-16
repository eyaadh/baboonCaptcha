import os
import time
import asyncio
import random
import secrets
import logging
import configparser
from tinydb import TinyDB, Query
from captcha.image import ImageCaptcha
from pyrogram.errors import MessageNotModified
from pyrogram import Client, idle, filters, emoji
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery \
    , ChatPermissions

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger(__name__)

is_env = bool(os.environ.get("ENV", None))
if is_env:
    tg_app_id = int(os.environ.get("TG_APP_ID"))
    tg_api_key = os.environ.get("TG_API_HASH")
    bot_api_key = os.environ.get("TG_BOT_TOKEN")
    bot_dustbin = int(os.environ.get("TG_BOT_DUSTBIN"))

    baboon = Client(
        api_id=tg_app_id,
        api_hash=tg_api_key,
        session_name=":memory:",
        bot_token=bot_api_key,
        workers=200
    )
else:
    app_config = configparser.ConfigParser()
    app_config.read("config.ini")
    bot_api_key = app_config.get("bot-configuration", "api_key")
    bot_dustbin = int(app_config.get("bot-configuration", "dustbin"))

    baboon = Client(
        session_name="baboon",
        bot_token=bot_api_key,
        workers=200
    )

image = ImageCaptcha(fonts=["font1.ttf"])

db = TinyDB("db.json")
db_query = Query()


@baboon.on_callback_query(filters.regex('^captcha.*'))
async def correct_captcha_cb_handler(c: Client, cb: CallbackQuery):
    cb_data = cb.data.split("_")
    if len(cb_data) > 1:
        secret = cb_data[1]
        cap_data = get_captcha(cb.message.chat.id, cb.message.message_id)
        f_user_id = cap_data[0]["user_id"]
        if f_user_id == cb.from_user.id:
            await cb.answer()
            user = await c.get_users(
                f_user_id
            )
            mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
            if secret == cap_data[0]["key_id"]:
                await c.restrict_chat_member(
                    cb.message.chat.id,
                    f_user_id,
                    ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_stickers=True,
                        can_send_animations=True,
                        can_send_games=True,
                        can_use_inline_bots=True,
                        can_add_web_page_previews=True,
                        can_send_polls=True
                    )
                )

                await cb.edit_message_reply_markup()
                await cb.edit_message_text(
                    f"{mention} has successfully solved the Captcha and verified."
                )

                remove_captcha(cb.message.chat.id, cb.message.message_id)
                await baboon.delete_messages(cb.message.chat.id, cb.message.message_id)
            else:
                await baboon.delete_messages(cb.message.chat.id, cb.message.message_id)
                await baboon.send_message(
                    chat_id=cb.message.chat.id,
                    text=f"{mention} has Failed to solve the Captcha."
                )

        else:
            await cb.answer(
                "This captcha is not for you.",
                show_alert=True
            )


@baboon.on_message(filters.new_chat_members)
async def on_new_chat_members(c: Client, m: Message):
    await c.restrict_chat_member(
        chat_id=m.chat.id,
        user_id=m.from_user.id,
        permissions=ChatPermissions()
    )

    secret = secrets.token_hex(2)

    buttons = []
    for x in range(2):
        bogus = secrets.token_hex(2)
        buttons.append(
            InlineKeyboardButton(
                text=bogus,
                callback_data=f"captcha_{bogus}"
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text=f"{secret}",
            callback_data=f"captcha_{secret}"
        )
    )

    random.shuffle(buttons)

    data = image.generate(secret)
    image.write(secret, f"{secret}.png")

    mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
    cap_message = await m.reply_photo(
        photo=f"{secret}.png",
        caption=f"{emoji.SHIELD} {mention}, To complete your Captcha select the correct Text "
                f"from the bellow options.",
        reply_markup=InlineKeyboardMarkup(
            [buttons]
        )
    )

    insert_captcha(
        key_id=secret,
        chat_id=m.chat.id,
        user_id=m.from_user.id,
        message_id=cap_message.message_id,
        m_time=time.time()
    )

    if os.path.isfile(f"{secret}.png"):
        os.remove(f"{secret}.png")

    await check_resolved(cap_message)


@baboon.on_message(filters.photo, group=3)
async def hide_pictures_handler(c: Client, m: Message):
    hid_message = await m.forward(
        chat_id=bot_dustbin
    )

    mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"

    await m.reply_text(
        f"I have hidden the photo sent by {mention}.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text=f"{emoji.FRAMED_PICTURE} Show me the Photo.",
                        callback_data=f"shp_{hid_message.message_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"{emoji.FRAMED_PICTURE} Add the Photo to Chat.",
                        callback_data=f"apc_{hid_message.message_id}_{m.chat.id}"
                    )
                ]
            ]
        )

    )

    await m.delete()


@baboon.on_callback_query(filters.regex('^shp.*'))
async def shp_cb_handler(c: Client, cb: CallbackQuery):
    cb_data = cb.data.split("_")
    if len(cb_data) > 1:
        msg_id = int(cb_data[1])

        await c.forward_messages(
            chat_id=cb.from_user.id,
            from_chat_id=bot_dustbin,
            message_ids=msg_id
        )

        await cb.answer()


@baboon.on_callback_query(filters.regex('^apc.*'))
async def apc_cb_handler(c: Client, cb: CallbackQuery):
    cb_data = cb.data.split("_")
    if len(cb_data) > 2:
        msg_id = int(cb_data[1])
        f_chat_id = int(cb_data[2])

        admins = await c.get_chat_members(chat_id=f_chat_id, filter="administrators")
        admin_list = [
            admin.user.id
            for admin in admins
        ]

        if cb.from_user.id in admin_list:
            await c.forward_messages(
                chat_id=f_chat_id,
                from_chat_id=bot_dustbin,
                message_ids=msg_id
            )

            await cb.message.delete()
            await cb.answer()
        else:
            await cb. answer(
                "You need to be an admin to approve this photo to be added to the chat permanently!",
                show_alert=True
            )


async def check_resolved(msg):
    while True:
        cap_data = get_captcha(msg.chat.id, msg.message_id)
        await asyncio.sleep(1)
        if len(cap_data) > 0 and (time.time() - cap_data[0]["m_time"] > 20):
            user = await baboon.get_users(
                cap_data[0]["user_id"]
            )

            mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

            try:

                await baboon.delete_messages(msg.chat.id, msg.message_id)
                await baboon.send_message(
                    chat_id=msg.chat.id,
                    text=f"{mention} has Failed to solve the Captcha within the given time period."
                )

            except MessageNotModified as e:
                pass

            remove_captcha(msg.chat.id, msg.message_id)
        elif len(cap_data) < 1:
            break


def get_captcha(chat_id, message_id):
    return db.search((db_query.chat_id == chat_id) & (db_query.message_id == message_id))


def remove_captcha(chat_id, message_id):
    return db.remove((db_query.chat_id == chat_id) & (db_query.message_id == message_id))


def insert_captcha(key_id, chat_id, user_id, message_id, m_time):
    db.insert({"key_id": key_id, "chat_id": chat_id, "user_id": user_id, "message_id": message_id, "m_time": m_time})


async def main():
    await baboon.start()
    await idle()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
