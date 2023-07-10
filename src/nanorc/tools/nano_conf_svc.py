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

    cs = ConfServer()
    cs.start_conf_service(port)
    while not cs.is_ready():
        console.print("Confservice is not quite ready yet")
        from time import sleep
        sleep(0.1)

    console.print("Confservice is ready!")

    #global conf_data
    from nanorc.argval import validate_conf_name
    from pathlib import Path
    validate_conf_name({}, {}, name)
    #session['conf_data'][name] = s
    from nanorc.utils import get_json_recursive
    from requests import post, get
    header = {
        'Accept' : 'application/json',
        'Content-Type':'application/json'
    }

    import json
    try:
        r = post(
            f'http://0.0.0.0:{port}/configuration?name={name}',
            headers=header,
            data=json.dumps(get_json_recursive(Path(json_dir)))
        )
        console.print(f'Added \'{name}\' content:\n{r.json()}')
    except Exception as e:
        console.print(f'Added \'{name}\' insertion failed:\n{str(e)}')

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
