#!/usr/bin/env python3

"""
Command Line Interface for NanoRC
"""

from .cli import cli, logging
from .credmgr import credentials
from rich.console import Console
from nanorc.nano_context import NanoContext

def main():
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    console = Console()
    credentials.console = console # some uglyness right here
    obj = NanoContext(console)

    try:
        cli(obj=obj, show_default=True)
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()

if __name__ == '__main__':
    main()

