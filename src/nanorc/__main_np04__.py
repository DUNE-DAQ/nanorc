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
        from .credmgr import credentials
        credentials.add_login_from_file("rundb", "credentials_rundb")
        
    except Exception as e:
        console.log("[bold red]Cannot read run db credentials, you need to get the credentials_rundb.py file[/bold red]")
        console.log(e)
    

if __name__ == '__main__':
    main()

