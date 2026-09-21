import json
import math
import os
import random
import statistics
import urllib.parse
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO

import discord
from discord import app_commands
from discord.ext import commands
from duckduckgo_search import DDGS
from groq import Groq


MAX_RECENT_TURNS = 4
SUMMARY_TRIGGER = 6
MAX_SUMMARY_CHARS = 700
MODEL_NAME = "openai/gpt-oss-120b"


def search_web(query: str) -> str:
    if not query.strip():
        return "Query pencarian kosong."

    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=3)
    except Exception as exc:
        return f"Gagal mencari web: {exc}"

    if not results:
        return "Tidak ada hasil pencarian yang relevan."

    lines = []
    for item in results:
        title = item.get("title") or "Hasil pencarian"
        url = item.get("href") or item.get("url") or ""
        snippet = item.get("body") or item.get("snippet") or ""
        lines.append(f"- {title}: {url}\n  {snippet}")
    return "\n\n".join(lines)


def run_python_code(code: str) -> str:
    safe_builtins = {
        "abs": abs,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "pow": pow,
        "print": print,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
    }
    safe_globals = {
        "__builtins__": safe_builtins,
        "datetime": datetime,
        "math": math,
        "random": random,
        "statistics": statistics,
    }

    output_buffer = StringIO()
    try:
        with redirect_stdout(output_buffer):
            exec(code, safe_globals, {})
    except Exception as exc:
        return f"Error: {exc}"

    text = output_buffer.getvalue().strip()
    return text if text else "Kode berhasil dijalankan tanpa output."


def generate_image(prompt: str) -> str:
    encoded_prompt = urllib.parse.quote(prompt.strip())
    return (
        "https://image.pollinations.ai/prompt/"
        f"{encoded_prompt}?width=1024&height=1024&nologo=true"
    )


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
        normalized = text.strip()
        for prefix in ("!ask-groq", "!groq"):
            if normalized.lower().startswith(prefix):
                return normalized[len(prefix):].strip()
        return normalized

    def _tool_definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Cari informasi terbaru atau fakta dari web untuk pertanyaan yang membutuhkan data terkini.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Kata kunci pencarian web."},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_python_code",
                    "description": "Jalankan kode Python untuk kalkulasi, analisis data, atau manipulasi angka.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Kode Python yang akan dijalankan."},
                        },
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "Buat gambar berdasarkan deskripsi prompt visual.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Deskripsi prompt gambar."},
                        },
                        "required": ["prompt"],
                    },
                },
            },
        ]

    def _tool_executor(self, name: str, arguments: dict) -> str:
        if name == "search_web":
            return search_web(arguments.get("query", ""))
        if name == "run_python_code":
            return run_python_code(arguments.get("code", ""))
        if name == "generate_image":
            return generate_image(arguments.get("prompt", ""))
        return f"Tool {name} tidak dikenal."

    def _tool_choice_for(self, question: str) -> str | dict:
        """Paksa tool yang tepat untuk intent yang jelas agar Groq tidak salah membaca tool_choice."""
        normalized = question.lower()
        if any(keyword in normalized for keyword in (
            "cuaca", "berita", "terbaru", "hari ini", "sekarang", "cari di web",
            "search web", "informasi terbaru",
        )):
            tool_name = "search_web"
        elif any(keyword in normalized for keyword in (
            "buat gambar", "buatkan gambar", "generate image", "gambar ai",
            "ilustrasi", "lukiskan",
        )):
            tool_name = "generate_image"
        elif any(keyword in normalized for keyword in (
            "hitung", "kalkulasi", "jalankan python", "kode python", "analisis data",
        )):
            tool_name = "run_python_code"
        else:
            return "auto"

        return {
            "type": "function",
            "function": {"name": tool_name},
        }

    async def _ask_groq(self, user_id: int, question: str, reply_context: str | None = None) -> str:
        if not self.groq.api_key:
            return "GROQ_API_KEY belum diatur. Isi variabel environment tersebut di Railway atau file .env."

        history = self._history_for(user_id)
        prompt = history.build_context(question, reply_context)

        system_prompt = (
            "Kamu adalah asisten Discord yang cerdas, ramah, dan ringkas. "
            "Gunakan tool bila perlu: search_web untuk berita atau fakta terbaru; "
            "run_python_code untuk kalkulasi atau analisis data; "
            "generate_image untuk permintaan gambar. "
            "Jangan pakai tool untuk pertanyaan umum yang bisa dijawab tanpa alat. "
            "Jika kamu menggunakan tool, jelaskan hasilnya secara jelas dan singkat."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.groq.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=self._tool_definitions(),
                tool_choice=self._tool_choice_for(question),
                temperature=0.4,
                max_tokens=500,
            )
            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []

            if not tool_calls:
                content = (assistant_message.content or "").strip()
                return content or "Saya tidak punya jawaban yang jelas untuk itu."

            tool_call_payloads = []
            for call in tool_calls:
                tool_call_payloads.append({
                    "id": call.id,
                    "type": call.type,
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                })

            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": tool_call_payloads,
            })

            for call in tool_calls:
                args = json.loads(call.function.arguments)
                result = self._tool_executor(call.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result),
                })

            final_response = self.groq.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.4,
                max_tokens=500,
            )
            final_text = (final_response.choices[0].message.content or "").strip()
            return final_text or "Saya sudah menjalankan tool, tetapi tidak ada ringkasan final yang dikembalikan."
        except Exception as exc:
            return f"Gagal menghubungi Groq: {exc}"

    async def _resolve_reply_context(self, message: discord.Message) -> str | None:
        if message.reference is None:
            return None

        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message) and resolved.author == self.bot.user:
            return resolved.content.strip()

        try:
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

        if referenced_message.author == self.bot.user:
            return referenced_message.content.strip()
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        content = message.content.strip()
        if not content:
            return

        reply_context = await self._resolve_reply_context(message)

        mention_id = self.bot.user.id if self.bot.user else None
        has_mention = (
            mention_id is not None and (
                f"<@{mention_id}>" in content or f"<@!{mention_id}>" in content
            )
        )

        command_prefixes = ("!ask-groq", "!groq")
        if not (reply_context or has_mention or content.lower().startswith(command_prefixes)):
            return

        question = content
        if content.lower().startswith(command_prefixes):
            question = self._trim_question(content)
        elif has_mention:
            if mention_id is not None:
                question = content.replace(f"<@{mention_id}>", "", 1).replace(f"<@!{mention_id}>", "", 1).strip()

        if not question:
            await message.reply("Tulis pertanyaan setelah perintah, atau balas pesan bot lalu kirim pertanyaanmu.")
            return

        answer = await self._ask_groq(message.author.id, question, reply_context)

        if "https://image.pollinations.ai/" in answer:
            embed = discord.Embed(
                title="Hasil gambar AI",
                description="Berikut hasil gambar yang diminta.",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=answer)
            await message.reply(embed=embed)
            await self._remember(message.author.id, question, answer[:1000])
            return

        await message.reply(answer[:2000])
        await self._remember(message.author.id, question, answer[:1000])

    @app_commands.command(name="ask-groq", description="Tanya Groq dengan konteks ringkas per user.")
    @app_commands.describe(question="Pertanyaan Anda untuk Groq.")
    async def ask_groq(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()
        answer = await self._ask_groq(interaction.user.id, question)

        if "https://image.pollinations.ai/" in answer:
            embed = discord.Embed(
                title="Hasil gambar AI",
                description="Berikut hasil gambar yang diminta.",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=answer)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(answer[:2000])

        await self._remember(interaction.user.id, question, answer[:1000])

    @commands.command(name="ask-groq")
    async def ask_groq_text(self, ctx: commands.Context, *, question: str) -> None:
        if not question.strip():
            await ctx.reply("Tulis pertanyaan setelah `!ask-groq`.")
            return

        reply_context = await self._resolve_reply_context(ctx.message)
        answer = await self._ask_groq(ctx.author.id, question, reply_context)

        if "https://image.pollinations.ai/" in answer:
            embed = discord.Embed(
                title="Hasil gambar AI",
                description="Berikut hasil gambar yang diminta.",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=answer)
            await ctx.reply(embed=embed)
        else:
            await ctx.reply(answer[:2000])

        await self._remember(ctx.author.id, question, answer[:1000])

    @commands.command(name="groq")
    async def groq_text(self, ctx: commands.Context, *, question: str) -> None:
        await self.ask_groq_text(ctx, question=question)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GroqChat(bot))
