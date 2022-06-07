from datetime import datetime
from rich.console import Console
from rich.table import Table


class RunInfo:
    def __init__(self, run_number:int, run_type:str, run_start_time:datetime):
        self.run_number = run_number
        self.run_type = run_type
        self.run_start_time = run_start_time
        self.run_stop_time = None

    def finish_run(self):
        self.run_stop_time = datetime.now()

def start_run(run_number:int, run_type:int):
    ri = RunInfo(run_number, run_type, datetime.now())
    return ri


def print_run_info(run_info:RunInfo, console:Console):
    if run_info.run_stop_time:
        table = Table(title=f'Run [bold]#{run_info.run_number}[/bold] finished',show_header=False)
    else:
        table = Table(title=f'Run [bold]#{run_info.run_number}[/bold] [red]ongoing[/red]',show_header=False)

    table.add_row("Type", run_info.run_type)
    start_time = run_info.run_start_time.strftime("%d/%m/%Y %H:%M:%S")
    table.add_row("Start time", start_time)
    if run_info.run_stop_time:
        stop_time = run_info.run_stop_time.strftime("%d/%m/%Y %H:%M:%S")
        table.add_row("Stop time", stop_time)
        run_length = run_info.run_stop_time-run_info.run_start_time
        table.add_row("Duration", str(run_length))

    console.print(table)
