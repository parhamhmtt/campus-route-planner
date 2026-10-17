"""Natural-language chatbot for the campus route planner (Claude tool use).

The model only decides which tool to call and explains the result. All routes,
costs and reservations come from the algorithms in this package via
``tools.PlannerSession``.

Run:  python -m campus_route_planner chat
Needs the ANTHROPIC_API_KEY environment variable.
"""

import argparse
import json
import os
import sys

from .graph_data import DEFAULT_SAVE_PATH
from .tools import DEFAULT_OUTPUT_DIR, TOOL_SCHEMAS, PlannerSession

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 2048
MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT = """\
You are the assistant for Campus Route Planner, a shuttle-route tool for universities.
Universities are nodes and shuttle routes are weighted edges (the weight is an abstract
travel cost or distance, with no unit).

Rules:
- Use the tools for every fact about the network and for every calculation. Never work
  out routes, costs, spanning trees or visit orders yourself, and never invent
  universities, routes, weights or reservations.
- If a university name is not found, use the suggestions in the error. If you are still
  unsure which one the user means, ask instead of guessing.
- Ask for missing details (connections, weights, student priority) instead of making
  them up.
- Before removing a university, confirm with the user unless they already asked for
  exactly that.
- Reservations: a lower priority number means higher priority. Once a route is full,
  new requests are rejected.
- Multi-stop trips are open paths (start and end chosen freely), not round trips.
- When the user wants to see a picture, call save_plot and tell them the file path.
- Keep answers short and plain. Do not repeat raw JSON.
"""


class ChatBot:
    """Conversation with Claude, with the planner tools attached."""

    def __init__(self, session, client, model=DEFAULT_MODEL, on_tool_call=None,
                 max_tool_rounds=MAX_TOOL_ROUNDS):
        self.session = session
        self.client = client
        self.model = model
        self.on_tool_call = on_tool_call
        self.max_tool_rounds = max_tool_rounds
        self.messages = []

    def reset(self):
        self.messages = []

    def ask(self, text):
        """Send one user message, run any requested tools, return Claude's reply."""
        start = len(self.messages)
        self.messages.append({"role": "user", "content": text})
        try:
            return self._run_until_answer(start)
        except BaseException:
            # never leave a half-finished tool exchange in the history
            del self.messages[start:]
            raise

    def _run_until_answer(self, start):
        for _ in range(self.max_tool_rounds):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text").strip()

            if response.stop_reason != "tool_use":
                if any(b.type == "tool_use" for b in response.content):
                    # cut off mid tool call: a tool_use without a tool_result would
                    # make every later request fail, so forget this exchange
                    del self.messages[start:]
                    return "That reply was cut off before I could finish. Please try again."
                if response.stop_reason == "max_tokens":
                    text += "\n[The reply was cut off. Ask me to continue.]"
                return text or "(no reply)"

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if self.on_tool_call:
                    self.on_tool_call(block.name, block.input)
                output = self.session.call(block.name, block.input)
                result = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output),
                }
                if "error" in output:
                    result["is_error"] = True
                results.append(result)
            self.messages.append({"role": "user", "content": results})

        del self.messages[start:]
        return ("I stopped because that took too many tool calls in a row. "
                "Please try a simpler request.")


# --------------------------------------------------------------------------- #
# terminal chat
# --------------------------------------------------------------------------- #
HELP = """\
Ask in plain English, for example:
  What is the shortest way from Sharif to Beheshti?
  Plan a trip that visits Sharif, Kharazmi and Beheshti.
  Add Allameh in the West region, connected to Tehran with weight 5.
  Reserve a seat for Sara on Sharif-Tehran, priority 1.
  Draw the MST.
Commands: /reset (forget the conversation), /help, /quit"""


def explain_error(err):
    if type(err).__name__ == "AuthenticationError":
        return "Authentication failed. Check your ANTHROPIC_API_KEY."
    return f"Could not get a reply: {type(err).__name__}: {err}"


def run_repl(bot, input_fn=input, output_fn=print):
    output_fn("Campus Route Planner chat. Type /help for examples, /quit to leave.")
    while True:
        try:
            line = input_fn("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn("")
            break
        if not line:
            continue
        if line.lower() in ("/quit", "/exit", "quit", "exit"):
            break
        if line == "/help":
            output_fn(HELP)
            continue
        if line == "/reset":
            bot.reset()
            output_fn("Conversation cleared.")
            continue
        try:
            output_fn(f"bot> {bot.ask(line)}")
        except KeyboardInterrupt:
            output_fn("\n(interrupted)")
        except Exception as err:
            output_fn(explain_error(err))


def make_client():
    try:
        import anthropic
    except ImportError:
        sys.exit("The 'anthropic' package is missing. Run: pip install -r requirements.txt")
    return anthropic.Anthropic()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="campus_route_planner chat",
                                     description="Chat with the campus route planner.")
    parser.add_argument("--model", default=os.environ.get("CAMPUS_CHAT_MODEL", DEFAULT_MODEL),
                        help=f"Claude model (default: {DEFAULT_MODEL})")
    parser.add_argument("--data", default=str(DEFAULT_SAVE_PATH),
                        help="graph file shared with the menu CLI")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR),
                        help="folder for saved plots")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set the ANTHROPIC_API_KEY environment variable first, e.g.\n"
                 "  export ANTHROPIC_API_KEY=sk-ant-...")

    session = PlannerSession(save_path=args.data, output_dir=args.output)
    show = lambda name, args_: print(f"  [tool] {name}({json.dumps(args_)})")
    bot = ChatBot(session, make_client(), model=args.model, on_tool_call=show)
    run_repl(bot)


if __name__ == "__main__":
    main()
