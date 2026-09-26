import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("discord_bot")


class DiscordBot(commands.Bot):
	def __init__(self) -> None:
		intents = discord.Intents.default()
		intents.message_content = True
		intents.members = os.getenv("DISCORD_MEMBERS_INTENT", "false").lower() == "true"
		super().__init__(command_prefix=commands.when_mentioned, intents=intents)

	async def setup_hook(self) -> None:
		await self.load_extension("cogs.ping")
		await self.load_extension("cogs.random_person")
		await self.load_extension("cogs.groq_chat")
		await self.load_extension("cogs.link_converter")
		synced_commands = await self.tree.sync()
		logger.info("Synchronized %d application command(s)", len(synced_commands))

	async def on_ready(self) -> None:
		if self.user is not None:
			logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)


def main() -> None:
	token = os.getenv("DISCORD_TOKEN")
	if not token:
		raise RuntimeError(
			"DISCORD_TOKEN belum diatur. Salin .env.example menjadi .env "
			"dan isi token bot Discord."
		)

	bot = DiscordBot()
	bot.run(token, log_handler=None)


if __name__ == "__main__":
	main()
