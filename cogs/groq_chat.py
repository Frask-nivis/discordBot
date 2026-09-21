import os

import discord
from discord import app_commands
from discord.ext import commands
from groq import Groq


MAX_RECENT_TURNS = 4
SUMMARY_TRIGGER = 6
MAX_SUMMARY_CHARS = 700
MODEL_NAME = "openai/gpt-oss-120b"


class UserHistory:
    """History ringan per user: summary + beberapa turn terbaru."""

    def __init__(self) -> None:
        self.summary = ""
        self.recent: list[dict[str, str]] = []

    def add_turn(self, user_text: str, bot_reply: str) -> None:
        self.recent.append({
            "user": user_text[:1000],
            "bot": bot_reply[:1000],
        })
        if len(self.recent) > MAX_RECENT_TURNS:
            self.recent = self.recent[-MAX_RECENT_TURNS:]

    def build_context(self, current_question: str, reply_context: str | None = None) -> str:
        parts: list[str] = []

        if self.summary:
            parts.append(f"Ringkasan penting percakapan sebelumnya:\n{self.summary}")

        if self.recent:
            recent_lines = []
            for turn in self.recent:
                recent_lines.append(f"User: {turn['user']}\nBot: {turn['bot']}")
            parts.append("Percakapan terbaru:\n" + "\n---\n".join(recent_lines))

        if reply_context:
            parts.append(f"Konteks balasan user:\n{reply_context}")

        parts.append(f"Pertanyaan baru:\n{current_question}")
        return "\n\n".join(parts)


class GroqChat(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.groq = Groq(api_key=os.getenv("GROQ_API_KEY") or "")
        self.user_histories: dict[int, UserHistory] = {}

    def _history_for(self, user_id: int) -> UserHistory:
        history = self.user_histories.get(user_id)
        if history is None:
            history = UserHistory()
            self.user_histories[user_id] = history
        return history

    async def _summarize_history(self, history: UserHistory) -> str:
        if not history.recent or not self.groq.api_key:
            return history.summary

        recent_text = "\n\n".join(
            f"User: {turn['user']}\nBot: {turn['bot']}" for turn in history.recent
        )

        try:
            response = self.groq.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Buat ringkasan singkat, maksimal 5 bullet, dari percakapan berikut. "
                            "Fokus pada point penting, keputusan, preferensi, dan kebutuhan user.\n\n"
                            f"{recent_text}"
                        ),
                    }
                ],
                temperature=0.2,
                max_tokens=180,
            )
            summary = (response.choices[0].message.content or "").strip()
            if summary:
                return summary[:MAX_SUMMARY_CHARS]
        except Exception:
            pass

        return history.summary

    async def _remember(self, user_id: int, user_text: str, bot_reply: str) -> None:
        history = self._history_for(user_id)
        history.add_turn(user_text, bot_reply)

        if len(history.recent) >= SUMMARY_TRIGGER:
            summary = await self._summarize_history(history)
            if summary:
                history.summary = summary
                history.recent = history.recent[-3:]

    def _trim_question(self, text: str) -> str:
        return text.strip().replace("!ask-groq", "", 1).strip()

    async def _ask_groq(self, user_id: int, question: str, reply_context: str | None = None) -> str:
        if not self.groq.api_key:
            return "GROQ_API_KEY belum diatur. Isi variabel environment tersebut di Railway atau file .env."

        history = self._history_for(user_id)
        prompt = history.build_context(question, reply_context)

        try:
            response = self.groq.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah asisten yang ringkas, jelas, dan berguna. "
                            "Gunakan ringkasan percakapan sebelumnya jika ada, tapi tetap fokus "
                            "pada pertanyaan terbaru. Jangan bertele-tele."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.7,
                max_tokens=300,
            )
            answer = (response.choices[0].message.content or "").strip()
            if not answer:
                return "Groq tidak mengembalikan jawaban. Coba ulang pertanyaan lain."
            return answer
        except Exception as exc:
            return f"Gagal menghubungi Groq: {exc}"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        content = message.content.strip()
        if not content:
            return

        reply_context = None
        if message.reference is not None:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message) and resolved.author == self.bot.user:
                reply_context = resolved.content.strip()

        mention_id = self.bot.user.id if self.bot.user else None
        has_mention = (
            mention_id is not None and (
                f"<@{mention_id}>" in content or f"<@!{mention_id}>" in content
            )
        )

        if not (reply_context or has_mention or content.lower().startswith("!ask-groq")):
            return

        question = content
        if content.lower().startswith("!ask-groq"):
            question = self._trim_question(content)
        elif has_mention:
            if mention_id is not None:
                question = content.replace(f"<@{mention_id}>", "", 1).replace(f"<@!{mention_id}>", "", 1).strip()

        if not question:
            await message.reply("Tulis pertanyaan setelah perintah, atau balas pesan bot lalu kirim pertanyaanmu.")
            return

        answer = await self._ask_groq(message.author.id, question, reply_context)
        sent = await message.reply(answer[:2000])
        await self._remember(message.author.id, question, answer[:1000])

    @app_commands.command(name="ask-groq", description="Tanya Groq dengan konteks ringkas per user.")
    @app_commands.describe(question="Pertanyaan Anda untuk Groq.")
    async def ask_groq(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()
        answer = await self._ask_groq(interaction.user.id, question)
        await interaction.followup.send(answer[:2000])
        await self._remember(interaction.user.id, question, answer[:1000])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GroqChat(bot))
