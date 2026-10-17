import sys


def run():
    try:
        from .gui import main
    except ModuleNotFoundError as err:
        if err.name != "tkinter":
            raise
        sys.exit("tkinter is missing. On Ubuntu or Debian run: sudo apt install python3-tk")
    main()


if __name__ == "__main__":
    run()
