from datetime import datetime
from rich.console import Console
from rich.table import Table


class RunInfo:
    def __init__(self,
                 run_number:int,
                 run_type:str,
                 run_start_time:datetime,
                 message:str,
                 enable_data_storage:bool):
        self.run_number = run_number
        self.run_type = run_type
        self.run_start_time = run_start_time
        self.run_stop_time = None
        self.messages = [message]
        self.enable_data_storage = enable_data_storage
        self.trigger_interval_ticks = None

    def finish_run(self):
        self.run_stop_time = datetime.now()

    def is_running(self):
        return not self.run_stop_time

def start_run(run_number:int, run_type:int, message:str, enable_data_storage:bool):
    ri = RunInfo(
        run_number=run_number,
        run_type=run_type,
        run_start_time=datetime.now(),
        message=message,
        enable_data_storage=enable_data_storage
    )
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

    table.add_row("Data storage enabled", str(run_info.enable_data_storage))
    if run_info.trigger_interval_ticks:
        table.add_row("Trigger interval ticks", str(run_info.trigger_interval_ticks))
    else:
        table.add_row("Trigger interval ticks", "default (1Hz?)")
    i=0
    for message in run_info.messages:
        if message:
            table.add_row(f"Message #{i}", message)
            i+=1


    console.print(table)
