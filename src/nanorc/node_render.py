from .statefulnode import StatefulNode
from .node import *
from .k8spm import K8sProcess
from anytree import RenderTree, PreOrderIter
import logging as log
from rich.console import Console
import sh

def status_data(node, get_children=True) -> dict:
    ret = {}
    if isinstance(node, ApplicationNode):
        sup = node.sup
        if sup.desc.proc.is_alive():
            ret['process_state'] = 'alive'
        else:
            try:
                exit_code = sup.desc.proc.exit_code
            except sh.ErrorReturnCode as e:
                exit_code = e.exit_code
            ret['process_state'] = f'dead[{exit_code}]'
        ret['ping'] = sup.commander.ping()
        ret['last_cmd_failed'] = (sup.last_sent_command != sup.last_ok_command)
        ret['name'] = node.name
        ret['state'] = node.state + ("" if node.included else " - excluded")
        ret['host'] = sup.desc.host,
        ret['last_sent_command'] = sup.last_sent_command
        ret['last_ok_command'] = sup.last_ok_command
    else:
        ret['name'] = node.name
        ret['state'] = node.state
        if get_children:
            ret['children'] = [status_data(child) for child in node.children]
    return ret


def print_status(topnode, console, apparatus_id='', partition='') -> int:
    table = Table(title=f"[bold]{apparatus_id}[/bold] applications" + (f" in partition [bold]{partition}[/bold]" if partition else ''))
    table.add_column("name", style="blue")
    table.add_column("state", style="blue")
    table.add_column("host", style="magenta")
    table.add_column("pings", style="magenta")
    table.add_column("last cmd")
    table.add_column("last succ. cmd", style="green")

    for pre, _, node in RenderTree(topnode):
        if isinstance(node, ApplicationNode):
            sup = node.sup

            if sup.desc.proc.is_alive():
                alive = 'alive'
            else:
                proc = sup.desc.proc
                exit_code = None
                if isinstance(proc, K8sProcess): # hacky way to check the pm
                    exit_code = sup.desc.proc.status()
                else:
                    try:
                        exit_code = sup.desc.proc.exit_code
                    except sh.ErrorReturnCode as e:
                        exit_code = e.exit_code

                alive = f'dead[{exit_code}]'

            ping = sup.commander.ping()
            last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)

            state_str = Text()
            if not node.included:
                state_str = Text(f"{node.state} - {alive} - excluded")
            elif node.is_error():
                state_str = Text(f"{node.state} - {alive}", style=('bold red'))
            else:
                state_str = Text(f"{node.state} - {alive}")

            table.add_row(
                Text(pre)+Text(node.name),
                state_str,
                sup.desc.host,
                str(ping),
                Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                str(sup.last_ok_command)
            )

        else:
            state_str = node.state
            if not node.included:
                state_str = Text(f"{node.state} - excluded")
            table.add_row(Text(pre)+Text(node.name),
                          Text(f"{state_str}", style=('bold red' if node.is_error() else "")))

    console.print(table)

def print_node(node, console, leg:bool=False) -> int:
    rows = []
    try:
        for pre, _, all_node in RenderTree(node):
            if all_node == node:
                rows.append(f"{pre}[red]{all_node.name}[/red]")
            elif isinstance(all_node, SubsystemNode):
                rows.append(f"{pre}[yellow]{all_node.name}[/yellow]")
            elif isinstance(all_node, ApplicationNode):
                rows.append(f"{pre}[blue]{all_node.name}[/blue]")
            else:
                rows.append(f"{pre}{all_node.name}")

        console.print(Panel.fit('\n'.join(rows)))

        if leg:
            console.print("\nLegend:")
            console.print(" - [red]top node[/red]")
            console.print(" - [yellow]subsystems[/yellow]")
            console.print(" - [blue]applications[/blue]\n")

    except Exception as ex:
        console.print("Tree is corrupted!")
        return_code = 14
        raise RuntimeError("Tree is corrupted")
    return 0
