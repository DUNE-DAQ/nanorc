#!/usr/bin/env python3

import click
import click_shell

@click_shell.shell(prompt='dummy>')
def dummy():
    pass

@dummy.command()
def cmd1():
    pass


if __name__ == '__main__':
    # dummy()
    # 
    import logging
    from rich.logging import RichHandler
    from rich.pretty import Pretty

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )

    log = logging.getLogger("rich")
    log.info({"aa": "bb"})
    try:
        print(1 / 0)
    except Exception:
        log.exception("unable print!")