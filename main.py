import os
import asyncio
import random
import secrets
import logging
import configparser
from captcha.image import ImageCaptcha
from pyrogram import Client, idle, filters, emoji
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery \
    , ChatPermissions

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger(__name__)

app_config = configparser.ConfigParser()
app_config.read("config.ini")
bot_api_key = app_config.get("bot-configuration", "api_key")

baboon = Client(
    session_name="baboon",
    bot_token=bot_api_key,
    workers=200
)

image = ImageCaptcha(fonts=["font1.ttf"])


@baboon.on_callback_query(filters.regex('^wrong.*'))
async def wrong_captcha_cb_handler(c: Client, cb: CallbackQuery):
    cb_data = cb.data.split("_")
    if len(cb_data) > 1:
        f_user_id = int(cb_data[1])
        if f_user_id == cb.from_user.id:
            await cb.answer(
                "You have failed to verify the captcha",
                show_alert=True
            )
        else:
            await cb.answer(
                "This captcha is not for you.",
                show_alert=True
            )


@baboon.on_callback_query(filters.regex('^correct.*'))
async def correct_captcha_cb_handler(c: Client, cb: CallbackQuery):
    cb_data = cb.data.split("_")
    if len(cb_data) > 1:
        f_user_id = int(cb_data[1])
        if f_user_id == cb.from_user.id:
            await cb.answer()

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

            user = await c.get_users(f_user_id)
            mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

            await cb.edit_message_text(
                f"{mention} has successfully solved the Captcha and verified."
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
        buttons.append(
            InlineKeyboardButton(
                text=f"{secrets.token_hex(2)}",
                callback_data=f"wrong_{m.from_user.id}"
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text=f"{secret}",
            callback_data=f"correct_{m.from_user.id}"
        )
    )

    random.shuffle(buttons)

    data = image.generate(secret)
    image.write(secret, f"{secret}.png")

    mention = f"<a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>"
    await m.reply_photo(
        photo=f"{secret}.png",
        caption=f"{emoji.SHIELD} {mention}, To complete your Captcha select the correct Text "
                f"from the bellow options.",
        reply_markup=InlineKeyboardMarkup(
            [buttons]
        )
    )

    if os.path.isfile(f"{secret}.png"):
        os.remove(f"{secret}.png")


async def main():
    await baboon.start()
    await idle()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
