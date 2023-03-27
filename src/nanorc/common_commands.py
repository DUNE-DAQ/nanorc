import nanorc.argval as argval
from nanorc.nano_context import NanoContext
import click
from .statefulnode import CanExecuteReturnVal

def check_rc(ctx, rc):
    if not ctx.parent: return
    if ctx.parent.invoked_subcommand == '*' and rc.return_code:
        ctx.exit(rc.return_code)


def accept_timeout(default_timeout):
    def add_decorator(function):
        return click.option('--timeout', type=int, default=default_timeout, help="Timeout, in seconds", callback=argval.validate_timeout)(function)
    return add_decorator

def accept_path(argument:bool=False):
    def add_decorator(function):
        if argument:
            return click.argument('node-path', type=str, callback=argval.validate_node_path)(function)
        else:
            return click.option('--node-path', type=str, default=None, callback=argval.validate_node_path)(function)
    return add_decorator

def accept_message(argument:bool=False):
    def add_decorator(function):
        if argument:
            return click.argument('message', type=str)(function)
        else:
            return click.option('--message', type=str, default="")(function)
    return add_decorator

def accept_wait():
    def add_decorator(function):
        return click.option('--wait', type=int, default=0, help="Seconds to wait between commands", callback=argval.validate_wait)(function)
    return add_decorator

def add_run_end_parameters():
    # sigh start...
    def add_decorator(function):
        f1 = accept_timeout(None)(function)
        f2 = click.option('--force', default=False, is_flag=True)(f1)
        return click.option('--message', type=str, default="")(f2)
     # sigh end
    return add_decorator

@click.command()
@accept_message(argument=True)
@click.pass_obj
def message(obj, message):
    obj.rc.message(message)


@click.command()
@click.pass_obj
def status(obj: NanoContext):
    obj.rc.status()


@click.command()
@click.option('--legend', type=bool, is_flag=True, default=False)
@click.pass_obj
def ls(obj, legend):
    obj.rc.ls(leg=legend)


@click.command()
@click.option('--pin-thread-file', type=click.Path(exists=True), default=None)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def pin_threads(ctx, obj:NanoContext, pin_thread_file, timeout:int):
    data = { "script_name": 'thread_pinning' }
    if pin_thread_file:
        data["env"]: { "DUNEDAQ_THREAD_PIN_FILE": pin_thread_file }
    obj.rc.execute_script(data=data, timeout=timeout)


@click.command()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def boot(ctx, obj, timeout:int):
    obj.rc.boot(timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@click.pass_obj
@click.pass_context
def ls_thread(ctx, obj):
    obj.rc.ls_thread()


@click.command()
@accept_path()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def conf(ctx, obj, node_path, timeout:int):
    obj.rc.conf(node_path=node_path, timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@click.option('--force', default=False, is_flag=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def disable_triggers(ctx, obj, timeout, force):
    obj.rc.disable_triggers(
        timeout=timeout,
        force=force,
    )
    check_rc(ctx,obj.rc)
    obj.rc.status()

@click.command()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def enable_triggers(ctx, obj, **kwargs):
    obj.rc.enable_triggers(**kwargs)
    check_rc(ctx,obj.rc)
    obj.rc.status()

@click.command()
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def drain_dataflow(ctx, obj, **kwargs):
    obj.rc.drain_dataflow(**kwargs)
    check_rc(ctx,obj.rc)
    obj.rc.status()

@click.command()
@accept_timeout(None)
@click.option('--force', default=False, is_flag=True)
@click.pass_obj
@click.pass_context
def stop_trigger_sources(ctx, obj, **kwargs):
    obj.rc.stop_trigger_sources(**kwargs)
    check_rc(ctx,obj.rc)
    obj.rc.status()

@click.command()
@accept_timeout(None)
@click.option('--force', default=False, is_flag=True)
@click.pass_obj
@click.pass_context
def stop(ctx, obj, **kwargs):
    obj.rc.stop(**kwargs)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_wait()
@click.option('--force', default=False, is_flag=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def terminate(ctx, obj, wait:int, timeout:int, force:bool):
    obj.rc.terminate(
        timeout=timeout,
        force=force,
    )
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_wait()
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def shutdown(ctx, obj, wait:int, **kwargs):
    kwargs['node_path'] = None
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        wait = wait,
        command = 'shutdown',
        force = kwargs['force'],
        cmd_args = kwargs
    )

@click.command()
@accept_wait()
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def stop_run(ctx, obj, wait:int, **kwargs):
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        command = 'stop_run',
        force = kwargs['force'],
        wait = wait,
        cmd_args = kwargs
    )

@click.command()
@accept_path()
@click.option('--force', default=False, is_flag=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def scrap(ctx, obj, node_path, force, timeout):
    obj.rc.scrap(node_path=node_path, force=force, timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@click.argument('trigger-rate', type=float)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def change_rate(ctx, obj, trigger_rate, timeout):
    obj.rc.change_rate(trigger_rate, timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path(argument=True)
@click.option('--resource-name', type=str, default=None)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def include(ctx, obj, node_path, resource_name, timeout):
    if not resource_name:
        resource_name = node_path.name
    obj.rc.include(node_path=node_path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path(argument=True)
@click.option('--resource-name', type=str, default=None)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def exclude(ctx, obj, node_path, resource_name, timeout):
    if not resource_name:
        resource_name = node_path.name
    obj.rc.exclude(node_path=node_path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path(argument=True)
@click.argument('json_file', type=click.Path(exists=True))
@accept_timeout(None)
@click.pass_obj
def expert_command(obj, node_path, json_file, timeout):
    obj.rc.send_expert_command(
        node_path=node_path,
        json_file=json_file,
        timeout=timeout
    )


@click.command()
@click.pass_obj
@click.argument('seconds', type=int)
def wait(obj, seconds):
    from rich.progress import (Progress, SpinnerColumn, BarColumn, TextColumn,
                               TimeRemainingColumn, TimeElapsedColumn)
    import time

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=obj.console,
    ) as progress:
        waiting = progress.add_task("[yellow]waiting", total=seconds)

        for _ in range(seconds):
            progress.update(waiting, advance=1)

            time.sleep(1)


@click.command()
@click.pass_obj
@click.pass_context
def start_shell(ctx, obj):
    from click_shell import make_click_shell

    ctx.command = obj.shell
    shell = make_click_shell(ctx,prompt=ctx.command.shell.prompt)
    shell.cmdloop()


def add_common_cmds(shell, end_of_run_cmds=True):
    shell.add_command(message             , 'message'             )
    shell.add_command(status              , 'status'              )
    shell.add_command(ls                  , 'ls'                  )
    shell.add_command(pin_threads         , 'pin_threads'         )
    shell.add_command(boot                , 'boot'                )
    shell.add_command(conf                , 'conf'                )
    shell.add_command(enable_triggers     , 'enable_triggers'     )
    shell.add_command(disable_triggers    , 'disable_triggers'    )
    shell.add_command(stop_trigger_sources, 'stop_trigger_sources')
    shell.add_command(stop                , 'stop'                )
    shell.add_command(scrap               , 'scrap'               )
    shell.add_command(terminate           , 'terminate'           )
    shell.add_command(change_rate         , 'change_rate'         )
    shell.add_command(include             , 'include'             )
    shell.add_command(exclude             , 'exclude'             )
    shell.add_command(expert_command      , 'expert_command'      )
    shell.add_command(wait                , 'wait'                )
    shell.add_command(start_shell         , 'start_shell'         )
    if end_of_run_cmds:
        shell.add_command(drain_dataflow      , 'drain_dataflow'      )
        shell.add_command(stop_run            , 'stop_run'            )
        shell.add_command(shutdown            , 'shutdown'            )
    # shell.add_command(ls_thread       , 'ls_thread'       )

def add_custom_cmds(cli, rc_cmd_exec, cmds):
    for c,d in cmds.items():
        arg_list = {}
        arg_default = {}
        for app_data in d:
            for modules_data in app_data.values():
                for module_data in modules_data:
                    module = module_data['match']
                    cmd_data = module_data.get('data')
                    if not cmd_data: continue
                    for arg in cmd_data:
                        arg_list[arg] = type(cmd_data[arg])
                        arg_default[arg] = cmd_data[arg]

        def execute_custom(ctx, obj, timeout, **kwargs):
            rc_cmd_exec(command=obj.info_name, data=kwargs, timeout=timeout)

        execute_custom = click.pass_obj(execute_custom)
        execute_custom = click.pass_context(execute_custom)
        execute_custom = click.command(c)(execute_custom)
        execute_custom = accept_timeout(None)(execute_custom)
        for arg, argtype in arg_list.items():
            arg_pretty = arg.replace("_", "-")
            execute_custom = click.option(f'--{arg_pretty}', type=argtype, default=arg_default[arg])(execute_custom)
        cli.add_command(execute_custom, c)


def execute_cmd_sequence(command:str, ctx, rc, wait:int, force:bool, cmd_args:dict):
    sequence = rc.get_command_sequence(command)
    import time
    last_cmd = sequence[-1]['cmd']

    for seq_cmd in sequence:
        cmd = seq_cmd['cmd']
        optional = seq_cmd['optional']
        canexec = rc.can_execute(cmd, quiet=True, check_children=False, check_inerror=False)

        if canexec == CanExecuteReturnVal.InvalidTransition:
            if optional:
                continue
            else:
                break

        canexec = rc.can_execute(cmd, check_inerror=True, check_dead=True, quiet=True, check_children=True)

        if canexec != CanExecuteReturnVal.CanExecute and not force:
            rc.log.error(f"Cannot execute '{cmd}' in the '{command}' reason: {str(canexec)}, you may be able to use --force")
            break

        rc.console.print(f'\n[underline]Executing \'{cmd}\'[/underline]\n')
        seq_func = getattr(rc, cmd, None)
        if not seq_func:
            rc.log.error(f"Function {cmd} doesn't exist in nanorc.core!")
            if not force: break

        seq_func(**cmd_args)

        check_rc(ctx, rc)

        if rc.return_code != 0 and not force:
            break

        if last_cmd != cmd:
            time.sleep(wait)
    rc.status()

