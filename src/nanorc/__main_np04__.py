#!/usr/bin/env python3

"""
Command Line Interface for NanoRC
"""

from .cli import *

@cli.command('start')
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.option('--resume-wait', type=int, default=0, help='Seconds to wait between Start and Resume commands')
@click.pass_obj
def start(obj:NanoContext, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int):
    """
    Start Command
    
    Args:
        obj (NanoContext): Context object
        run (int): Run number
        disable_data_storage (bool): Flag to disable data writing to storage
    
    """
    obj.rc.start(run, disable_data_storage)
    obj.rc.status()
    time.sleep(resume_wait)
    obj.rc.resume(trigger_interval_ticks)
    obj.rc.status()




def main():
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console()
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

