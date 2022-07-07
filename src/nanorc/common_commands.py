import nanorc.argval as argval
from nanorc.nano_context import NanoContext
import click

def check_rc(ctx, rc):
    if not ctx.parent: return
    if ctx.parent.invoked_subcommand == '*' and rc.return_code:
        ctx.exit(rc.return_code)


def accept_timeout(default_timeout):
    def add_decorator(function):
        return click.option('--timeout', type=int, default=default_timeout, help="Timeout, in seconds", callback=argval.validate_timeout)(function)
    return add_decorator

def accept_path():
    def add_decorator(function):
        return click.option('--path', type=str, default=None, callback=argval.validate_node_path)(function)
    return add_decorator

def accept_message(argument:bool=False):
    def add_decorator(function):
        if argument:
            return click.argument('message', type=str, default="")(function)
        else:
            return click.option('--message', type=str, default="")(function)
    return add_decorator

def accept_wait():
    def add_decorator(function):
        return click.option('--wait', type=int, default=0, help="Seconds to wait between commands", callback=argval.validate_wait)(function)
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
@click.pass_obj
def ls(obj):
    obj.rc.ls()


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
@accept_path()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def init(ctx, obj, path, timeout:int):
    obj.rc.init(path, timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def conf(ctx, obj, path, timeout:int):
    obj.rc.conf(path, timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start(ctx, obj:NanoContext, timeout:int):
    obj.rc.start(timeout=timeout)
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
        stop_sequence=False
    )
    check_rc(ctx,obj.rc)
    obj.rc.status()

@click.command()
@accept_wait()
@click.option('--force', default=False, is_flag=True)
@accept_message(argument=False)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def terminate(ctx, obj, wait:int, timeout:int, message:str, force:bool):
    obj.rc.terminate(
        timeout=timeout,
        force=force,
    )
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_wait()
@click.option('--force', default=False, is_flag=True)
@accept_message(argument=False)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def shutdown(ctx, obj, wait:int, timeout:int, message:str, force:bool):
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        wait = wait,
        command = 'shutdown',
        force = force,
        stop_sequence = True,
        timeout = timeout,
        message = message
    )

@click.command()
@accept_wait()
@click.option('--force', default=False, is_flag=True)
@accept_message(argument=False)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def stop_run(ctx, obj, wait:int, force:bool, message:str, timeout:int):
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        path = None,
        command = 'stop_run',
        force = force,
        wait = wait,
        stop_sequence = True,
        message = message,
        timeout = timeout,
    )



@click.command()
@accept_path()
@click.option('--force', default=False, is_flag=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def scrap(ctx, obj, path, force, timeout):
    obj.rc.scrap(path, force, timeout=timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_timeout(None)
@click.pass_obj
@click.pass_context
@click.command()
@click.argument('trigger-interval-ticks', type=int)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def change_rate(ctx, obj, trigger_interval_ticks, timeout):
    obj.rc.change_rate(trigger_interval_ticks, timeout)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path()
@click.option('--resource-name', type=str, required=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def include(ctx, obj, path, resource_name, timeout):
    obj.rc.include(path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@accept_path()
@click.option('--resource-name', type=str, required=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def exclude(ctx, obj, path, resource_name, timeout):
    obj.rc.exclude(path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj.rc)
    obj.rc.status()


@click.command()
@click.argument('app', type=str, default=None, callback=argval.validate_node_path)
@click.argument('json_file', type=click.Path(exists=True))
@accept_timeout(None)
@click.pass_obj
def expert_command(obj, app, json_file, timeout):
    obj.rc.send_expert_command(app, json_file, timeout=timeout)


@click.command()
@click.pass_obj
@click.argument('seconds', type=int)
def wait(obj, seconds):

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
@click.pass_context
def start_shell(ctx, obj):
    ctx.command = obj.shell
    shell = make_click_shell(ctx,prompt=ctx.command.shell.prompt)
    shell.cmdloop()


def add_common_cmds(shell):
    shell.add_command(message       , 'message'       )
    shell.add_command(status        , 'status'        )
    shell.add_command(ls            , 'ls'            )
    shell.add_command(pin_threads   , 'pin_threads'   )
    shell.add_command(boot          , 'boot'          )
    shell.add_command(init          , 'init'          )
    shell.add_command(conf          , 'conf'          )
    shell.add_command(start         , 'start'         )
    shell.add_command(stop_run      , 'stop_run'      )
    shell.add_command(scrap         , 'scrap'         )
    shell.add_command(terminate     , 'terminate'     )
    shell.add_command(shutdown      , 'shutdown'      )
    shell.add_command(change_rate   , 'change_rate'   )
    shell.add_command(include       , 'include'       )
    shell.add_command(exclude       , 'exclude'       )
    shell.add_command(expert_command, 'expert_command')
    shell.add_command(wait          , 'wait'          )
    shell.add_command(start_shell   , 'start_shell'   )


def add_custom_cmds(cli, rc_cmd_exec, cmds):
    for c,d in cmds.items():
        arg_list = {}
        arg_default = {}
        for app, app_data in d.items():
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


def execute_cmd_sequence(command:str, ctx, rc, wait:int, force:bool=False, skip_intermediate=False, **kwargs):
    sequence = rc.get_command_sequence(command)
    import time

    for seq_cmd in sequence:
        if not rc.can_execute(seq_cmd, quiet=True):
            if skip_intermediate:
                continue
            elif not force:
                rc.log.error(f"Cannot execute '{seq_cmd}' in the '{command}' sequence as the root node is '{rc.topnode.state}'!")
                break

        rc.console.print(f'Executing {seq_cmd}')
        seq_func = getattr(rc, seq_cmd, None)
        if not seq_func:
            rc.log.error(f"Function {seq_cmd} doesn't exist in nanorc.core, omitting!")
            if not force: break

        seq_func(**kwargs)

        check_rc(ctx, rc)
        rc.status()

        if rc.return_code != 0 and not force:
            break

        time.sleep(wait)
