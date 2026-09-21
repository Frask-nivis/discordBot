import asyncio
import unittest
from types import SimpleNamespace

from cogs.groq_chat import GroqChat, MODEL_NAME


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


class GroqChatTests(unittest.TestCase):
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

    def test_split_message_preserves_content_under_discord_limit(self):
        text = "baris\n" * 800
        chunks = GroqChat._split_message(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 2000 for chunk in chunks))
        self.assertEqual("".join(chunks), text)


if __name__ == "__main__":
    unittest.main()
