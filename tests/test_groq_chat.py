import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cogs.groq_chat import GroqChat, MODEL_NAME, ToolActivity, UserHistory, search_web


class FakeCompletions:
    def __init__(self):
        self.calls = []
        self.responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="search_web",
                                        arguments='{"query":"cuaca Jakarta hari ini"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="Cuaca sudah dicari.",
                            tool_calls=None,
                        )
                    )
                ]
            ),
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class RepeatingToolCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= 3:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id=f"call-{len(self.calls)}",
                                    type="function",
                                    function=SimpleNamespace(
                                        name="run_python_code",
                                        arguments='{"code":"print(1)"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Hasil kalkulasi sudah selesai.",
                        tool_calls=None,
                    )
                )
            ]
        )


class SingleToolCompletions:
    def __init__(self, tool_name):
        self.tool_name = tool_name
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            arguments = {
                "search_web": '{"query":"berita terbaru"}',
                "run_python_code": '{"code":"print(1)"}',
                "generate_image": '{"prompt":"kucing"}',
            }[self.tool_name]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    type="function",
                                    function=SimpleNamespace(
                                        name=self.tool_name,
                                        arguments=arguments,
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Tool selesai.",
                        tool_calls=None,
                    )
                )
            ]
        )


class FakeActivity:
    def __init__(self):
        self.updates = []

    async def update(self, tool_name, detail):
        self.updates.append((tool_name, detail))


class FakeActivityMessage:
    def __init__(self):
        self.edits = []
        self.deleted = False

    async def edit(self, **kwargs):
        self.edits.append(kwargs)

    async def delete(self):
        self.deleted = True


class GroqChatTests(unittest.TestCase):
    def test_message_routing_accepts_dm_and_guild_patterns(self):
        self.assertTrue(GroqChat._message_is_for_bot("!ferra halo", False, False))
        self.assertTrue(GroqChat._message_is_for_bot("halo", True, False))
        self.assertTrue(GroqChat._message_is_for_bot("halo", False, True))
        self.assertFalse(GroqChat._message_is_for_bot("halo", False, False))

    def test_activity_reuses_and_deletes_one_message(self):
        sent = []

        async def send(**kwargs):
            message = FakeActivityMessage()
            sent.append((message, kwargs))
            return message

        async def exercise():
            activity = ToolActivity(send)
            await activity.start()
            await activity.update("search_web", "Mencari berita")
            message = activity.message
            await activity.stop()
            return message

        message = asyncio.run(exercise())

        self.assertEqual(len(sent), 1)
        self.assertIsNotNone(message)
        self.assertEqual(len(message.edits), 1)
        self.assertTrue(message.deleted)

    def test_activity_updates_every_tool(self):
        for tool_name in ("search_web", "run_python_code", "generate_image"):
            completions = SingleToolCompletions(tool_name)
            cog = GroqChat.__new__(GroqChat)
            cog.groq = SimpleNamespace(
                api_key="test-key",
                chat=SimpleNamespace(completions=completions),
            )
            cog.user_histories = {}
            cog._tool_executor = lambda name, arguments: "hasil tool"
            activity = FakeActivity()

            result = asyncio.run(cog._ask_groq(1, "jalankan tool", activity=activity))

            self.assertEqual(result, "Tool selesai.")
            self.assertTrue(any(update[0] == tool_name for update in activity.updates))
            self.assertEqual(completions.calls[0]["model"], MODEL_NAME)

    def test_search_web_formats_results(self):
        fake_results = [
            {
                "title": "Berita terkini",
                "href": "https://example.com/news",
                "body": "Ringkasan berita.",
            }
        ]

        with patch("cogs.groq_chat.DDGS") as ddgs_class:
            ddgs_class.return_value.__enter__.return_value.text.return_value = fake_results

            result = search_web("berita terkini")

        self.assertIn("Berita terkini", result)
        self.assertIn("https://example.com/news", result)
        self.assertIn("Ringkasan berita.", result)

    def test_search_web_returns_provider_error(self):
        with patch("cogs.groq_chat.DDGS") as ddgs_class:
            ddgs_class.return_value.__enter__.return_value.text.side_effect = RuntimeError("provider down")

            result = search_web("berita terkini")

        self.assertIn("Gagal mencari web", result)
        self.assertIn("provider down", result)

    def test_reply_context_does_not_include_old_history(self):
        history = UserHistory()
        history.summary = "Topik lama yang tidak relevan"
        history.add_turn("Pertanyaan lama", "Jawaban lama")

        prompt = history.build_context("Tolong jelaskan bagian ini", "Pesan bot sebelumnya")

        self.assertIn("is-replying: true", prompt)
        self.assertIn("Pesan yang sedang dibalas", prompt)
        self.assertIn("PERTANYAAN USER TERBARU", prompt)
        self.assertNotIn("Topik lama yang tidak relevan", prompt)
        self.assertNotIn("Pertanyaan lama", prompt)

    def test_tool_flow_uses_explicit_auto_choice(self):
        completions = FakeCompletions()
        cog = GroqChat.__new__(GroqChat)
        cog.groq = SimpleNamespace(
            api_key="test-key",
            chat=SimpleNamespace(completions=completions),
        )
        cog.user_histories = {}
        cog._tool_executor = lambda name, arguments: "Hasil pencarian palsu"

        result = asyncio.run(cog._ask_groq(1, "cuaca Jakarta hari ini"))

        self.assertEqual(result, "Cuaca sudah dicari.")
        self.assertEqual(len(completions.calls), 2)
        for call in completions.calls:
            self.assertEqual(call["model"], MODEL_NAME)
            self.assertEqual(call["tool_choice"], "auto")
            self.assertTrue(call["tools"])

    def test_repeating_tool_calls_use_tool_free_final_request(self):
        completions = RepeatingToolCompletions()
        cog = GroqChat.__new__(GroqChat)
        cog.groq = SimpleNamespace(
            api_key="test-key",
            chat=SimpleNamespace(completions=completions),
        )
        cog.user_histories = {}
        cog._tool_executor = lambda name, arguments: "1"

        result = asyncio.run(cog._ask_groq(1, "hitung 1"))

        self.assertEqual(result, "Hasil kalkulasi sudah selesai.")
        self.assertEqual(len(completions.calls), 4)
        self.assertTrue(all(call["tool_choice"] == "auto" for call in completions.calls[:3]))
        self.assertNotIn("tools", completions.calls[3])
        self.assertNotIn("tool_choice", completions.calls[3])

    def test_split_message_preserves_content_under_discord_limit(self):
        text = "baris\n" * 800
        chunks = GroqChat._split_message(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))
        self.assertEqual("".join(chunks), text)


if __name__ == "__main__":
    unittest.main()
