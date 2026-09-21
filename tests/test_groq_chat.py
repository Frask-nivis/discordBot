import asyncio
import unittest
from types import SimpleNamespace

from cogs.groq_chat import GroqChat, MODEL_NAME, UserHistory


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


class GroqChatTests(unittest.TestCase):
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
