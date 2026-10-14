import json
import os
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from campus_route_planner import chatbot
from campus_route_planner.chatbot import SYSTEM_PROMPT, ChatBot, run_repl
from campus_route_planner.tools import TOOL_SCHEMAS, PlannerSession


# ---- scripted stand-in for anthropic.Anthropic ----------------------------- #
def text(t):
    return NS(type="text", text=t)


def tool(id_, tool_name, /, **arguments):
    return NS(type="tool_use", id=id_, name=tool_name, input=arguments)


def reply(*blocks, stop="end_turn"):
    return NS(content=list(blocks), stop_reason=stop)


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        kwargs["messages"] = list(kwargs["messages"])  # snapshot: the bot keeps appending
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeClient:
    def __init__(self, *script):
        self.messages = FakeMessages(script)


@pytest.fixture
def session(tmp_path):
    return PlannerSession(save_path=tmp_path / "graph.json", output_dir=tmp_path / "out")


def tool_results(message):
    assert message["role"] == "user"
    return message["content"]


# ---- the loop ------------------------------------------------------------- #
def test_plain_answer_without_tools(session):
    client = FakeClient(reply(text("Hello!")))
    bot = ChatBot(session, client)
    assert bot.ask("hi") == "Hello!"
    call = client.messages.calls[0]
    assert call["tools"] == TOOL_SCHEMAS
    assert call["system"] == SYSTEM_PROMPT
    assert call["model"] == chatbot.DEFAULT_MODEL
    assert call["messages"] == [{"role": "user", "content": "hi"}]


def test_tool_round_trip(session):
    seen = []
    client = FakeClient(
        reply(text("Checking."),
              tool("toolu_1", "find_shortest_path", source="sharif", destination="Beheshti"),
              stop="tool_use"),
        reply(text("It is 8 units via Tehran and Elm-o-Sanat.")),
    )
    bot = ChatBot(session, client, on_tool_call=lambda n, a: seen.append((n, a)))
    answer = bot.ask("Shortest path Sharif to Beheshti?")

    assert answer == "It is 8 units via Tehran and Elm-o-Sanat."
    assert seen == [("find_shortest_path", {"source": "sharif", "destination": "Beheshti"})]

    second = client.messages.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    (result,) = tool_results(second[2])
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_1"
    assert "is_error" not in result
    payload = json.loads(result["content"])
    assert payload["distance"] == 8 and payload["path"][0] == "Sharif"


def test_tool_errors_are_flagged_and_the_model_can_recover(session):
    client = FakeClient(
        reply(tool("t1", "find_shortest_path", source="Sharfi", destination="Beheshti"),
              stop="tool_use"),
        reply(tool("t2", "find_shortest_path", source="Sharif", destination="Beheshti"),
              stop="tool_use"),
        reply(text("Done.")),
    )
    bot = ChatBot(session, client)
    assert bot.ask("go") == "Done."
    (first,) = tool_results(client.messages.calls[1]["messages"][2])
    assert first["is_error"] is True
    assert "Did you mean: Sharif" in json.loads(first["content"])["error"]
    (second,) = tool_results(client.messages.calls[2]["messages"][4])
    assert "is_error" not in second


def test_parallel_tool_calls_answer_in_one_message(session):
    client = FakeClient(
        reply(tool("a", "get_minimum_spanning_tree"),
              tool("b", "find_shortest_path", source="Sharif", destination="Tehran"),
              stop="tool_use"),
        reply(text("ok")),
    )
    ChatBot(session, client).ask("both")
    results = tool_results(client.messages.calls[1]["messages"][2])
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


def test_unknown_tool_from_the_model_does_not_crash(session):
    client = FakeClient(reply(tool("x", "format_disk"), stop="tool_use"), reply(text("no")))
    ChatBot(session, client).ask("hi")
    (result,) = tool_results(client.messages.calls[1]["messages"][2])
    assert result["is_error"] and "Unknown tool" in result["content"]


def test_tools_change_state_across_turns_and_history_is_kept(session):
    client = FakeClient(
        reply(tool("1", "add_university", name="Allameh",
                   connections=[{"university": "Tehran", "weight": 5}]), stop="tool_use"),
        reply(text("Added.")),
        reply(tool("2", "find_shortest_path", source="Allameh", destination="Sharif"),
              stop="tool_use"),
        reply(text("8 units.")),
    )
    bot = ChatBot(session, client)
    bot.ask("add it")
    assert "Allameh" in session.uni.get_graph()
    assert bot.ask("route to Sharif?") == "8 units."
    third = client.messages.calls[3]["messages"]
    assert len(third) == 7  # whole conversation is sent each time
    assert json.loads(tool_results(third[6])[0]["content"])["distance"] == 8
    bot.reset()
    assert bot.messages == []


def test_api_failure_rolls_back_history(session):
    client = FakeClient(
        reply(tool("t1", "get_minimum_spanning_tree"), stop="tool_use"),
        RuntimeError("network down"),
        reply(text("back again")),
    )
    bot = ChatBot(session, client)
    with pytest.raises(RuntimeError):
        bot.ask("first")
    assert bot.messages == []  # no dangling tool_use / orphan user message
    assert bot.ask("second") == "back again"
    assert bot.messages[0] == {"role": "user", "content": "second"}


def test_runaway_tool_loop_is_stopped_and_history_stays_valid(session):
    loop = [reply(tool(f"t{i}", "list_universities"), stop="tool_use") for i in range(5)]
    bot = ChatBot(session, FakeClient(*loop), max_tool_rounds=3)
    assert "too many tool calls" in bot.ask("loop")
    assert bot.messages == []


def test_truncated_tool_call_is_dropped(session):
    client = FakeClient(reply(text("Let me"), tool("t1", "list_universities"), stop="max_tokens"))
    bot = ChatBot(session, client)
    assert "cut off" in bot.ask("hi")
    assert bot.messages == []


def test_truncated_text_reply_is_flagged(session):
    bot = ChatBot(session, FakeClient(reply(text("Partial"), stop="max_tokens")))
    answer = bot.ask("hi")
    assert answer.startswith("Partial") and "cut off" in answer


def test_empty_reply_has_a_fallback(session):
    assert ChatBot(session, FakeClient(reply(stop="refusal"))).ask("hi") == "(no reply)"


# ---- terminal chat -------------------------------------------------------- #
def drive(bot, *lines):
    feed = iter(lines)
    out = []

    def fake_input(prompt):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    run_repl(bot, input_fn=fake_input, output_fn=out.append)
    return out


def test_repl_commands_and_errors(session):
    client = FakeClient(reply(text("Hi there")), RuntimeError("boom"), reply(text("fresh")))
    bot = ChatBot(session, client)
    out = drive(bot, "", "hello", "/help", "second", "/reset", "third", "/quit", "ignored")
    joined = "\n".join(out)
    assert "bot> Hi there" in joined
    assert "Ask in plain English" in joined
    assert "Could not get a reply: RuntimeError: boom" in joined
    assert "Conversation cleared." in joined
    assert "bot> fresh" in joined
    assert len(client.messages.calls) == 3  # blank line and /commands never hit the API


def test_repl_ends_on_eof_and_ctrl_c(session):
    assert drive(ChatBot(session, FakeClient())) [-1] == ""
    bot = ChatBot(session, FakeClient())

    def interrupt(prompt):
        raise KeyboardInterrupt

    out = []
    run_repl(bot, input_fn=interrupt, output_fn=out.append)
    assert out[-1] == ""


def test_authentication_hint():
    class AuthenticationError(Exception):
        pass

    assert "ANTHROPIC_API_KEY" in chatbot.explain_error(AuthenticationError("401"))


# ---- entry points --------------------------------------------------------- #
def test_main_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        chatbot.main([])
    assert "ANTHROPIC_API_KEY" in str(exit_info.value)


def test_main_wires_everything_together(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = FakeClient()
    captured = {}
    monkeypatch.setattr(chatbot, "make_client", lambda: fake)
    monkeypatch.setattr(chatbot, "run_repl", lambda bot: captured.update(bot=bot))
    chatbot.main(["--model", "some-model", "--data", str(tmp_path / "g.json"),
                  "--output", str(tmp_path / "o")])
    bot = captured["bot"]
    assert bot.model == "some-model" and bot.client is fake
    assert bot.session.save_path == tmp_path / "g.json"
    assert bot.session.output_dir == tmp_path / "o"


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_python_m_chat_without_key_exits_cleanly():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run([sys.executable, "-m", "campus_route_planner", "chat"],
                          capture_output=True, text=True, env=env, cwd=REPO,
                          timeout=60, check=False)
    assert proc.returncode == 1
    assert "ANTHROPIC_API_KEY" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_menu_cli_still_starts_and_exits():
    proc = subprocess.run([sys.executable, "-m", "campus_route_planner"], input="12\n",
                          capture_output=True, text=True, cwd=REPO, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "Options:" in proc.stdout


def test_chat_subcommand_is_routed(monkeypatch):
    from campus_route_planner import __main__ as entry

    called = {}
    monkeypatch.setattr(chatbot, "main", lambda argv: called.update(argv=argv))
    monkeypatch.setattr(sys, "argv", ["prog", "chat", "--model", "m"])
    entry.run()
    assert called["argv"] == ["--model", "m"]


# ---- the real SDK, against a mock HTTP server ------------------------------ #
def test_wire_format_with_the_real_sdk(session):
    anthropic = pytest.importorskip("anthropic")
    try:
        import httpx2 as httpx  # newer SDK releases
    except ImportError:
        import httpx

    requests = []

    def message(content, stop_reason):
        return {"id": "msg_1", "type": "message", "role": "assistant",
                "model": "claude-sonnet-5-5", "content": content,
                "stop_reason": stop_reason, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5}}

    def handler(request):
        requests.append((request, json.loads(request.content)))
        if len(requests) == 1:
            body = message([
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "toolu_01", "name": "find_shortest_path",
                 "input": {"source": "sharif", "destination": "Beheshti"}},
            ], "tool_use")
        else:
            body = message([{"type": "text", "text": "It is 8 units."}], "end_turn")
        return httpx.Response(200, json=body)

    client = anthropic.Anthropic(
        api_key="sk-ant-test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert ChatBot(session, client).ask("shortest path?") == "It is 8 units."

    (req1, body1), (req2, body2) = requests
    assert req1.url.path == "/v1/messages" and req1.headers["x-api-key"] == "sk-ant-test"
    assert body1["model"] == chatbot.DEFAULT_MODEL and body1["system"] == SYSTEM_PROMPT
    assert len(body1["tools"]) == len(TOOL_SCHEMAS)
    assert all(t["input_schema"]["type"] == "object" for t in body1["tools"])

    # the assistant turn goes back exactly as received, then the tool result follows it
    assistant, results = body2["messages"][1], body2["messages"][2]
    assert assistant["role"] == "assistant"
    tool_use = [b for b in assistant["content"] if b["type"] == "tool_use"][0]
    assert tool_use["id"] == "toolu_01" and tool_use["name"] == "find_shortest_path"
    assert results["role"] == "user"
    assert results["content"][0]["type"] == "tool_result"
    assert results["content"][0]["tool_use_id"] == "toolu_01"
    assert json.loads(results["content"][0]["content"])["distance"] == 8
