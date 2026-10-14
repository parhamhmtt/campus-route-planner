import sys


def run():
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        from .chatbot import main as chat_main

        chat_main(sys.argv[2:])
    else:
        from .cli import main

        main()


if __name__ == "__main__":
    run()
