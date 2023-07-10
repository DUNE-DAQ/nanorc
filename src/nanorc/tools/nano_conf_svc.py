import click
from rich.console import Console
from nanorc.argval import validate_conf_name

console = Console()

@click.command()
@click.argument('json_dir', type=click.Path(exists=True), required=True)
@click.argument('name', type=str, required=True, callback=validate_conf_name)
@click.option('--port', type=int, default=None, help='Where the port for the service will be')
def svc(json_dir, name, port):
    from nanorc.confserver import ConfServer

    cs = ConfServer(port)

    console.print("Confservice is ready!")

    cs.add_configuration(name, json_dir)

    from requests import get
    try:
        r = get(
            f'http://0.0.0.0:{port}/configuration?name={name}'
        )
        console.print(f'\'{name}\' content:\n{r.json().keys()}')
    except Exception as e:
        console.print(f'Couldn\'t retrieve \'{name}\':\n{str(e)}')

    try:
        r = get(
            f'http://0.0.0.0:{port}/configuration'
        )
        console.print(f'Store content:\n{r.json()}')
    except Exception as e:
        console.print(f'Couldn\'t retrieve store content:\n{str(e)}')


    import signal
    def signal_handler(sig, frame):
        console.print('Finishing the ConfServer')
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
