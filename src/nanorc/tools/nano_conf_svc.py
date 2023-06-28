import click
from rich.console import Console
from nanorc.argval import validate_conf_name

console = Console()

@click.command()
@click.argument('json_dir', type=click.Path(exists=True), required=True)
@click.argument('name', type=str, required=True, callback=validate_conf_name)
@click.option('--port', type=int, default=None, help='Where the port for the service will be')
def svc(json_dir, name, port):
    import threading
    from nanorc.confserver import ConfServer

    cs = ConfServer({name: json_dir})

    thread = threading.Thread(target=cs.start_conf_service, name="conf-server", args = [port])
    thread.start()

    import signal
    def signal_handler(sig, frame):
        print('Finishing the ConfServer')
        cs.terminate()

    signal.signal(signal.SIGINT, signal_handler)

def main():
    try:
        svc()
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        console.log(e)
        console.print_exception()

if __name__ == '__main__':
    main()
