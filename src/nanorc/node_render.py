from .groupnode import GroupNode
from .node import *
from anytree import RenderTree
import logging as log
from rich.console import Console


def print_status(topnode, console, apparatus_id='') -> int:
    table = Table(title=f"{apparatus_id} apps")
    table.add_column("name", style="blue")
    table.add_column("state", style="blue")
    table.add_column("host", style="magenta")
    table.add_column("alive", style="magenta")
    table.add_column("pings", style="magenta")
    table.add_column("last cmd")
    table.add_column("last succ. cmd", style="green")

    for pre, _, node in RenderTree(topnode):
        if isinstance(node, ApplicationNode):
            sup = node.sup
            if sup.desc.proc.is_alive():
                alive = 'alive'
            else:
                try:
                    exit_code = sup.desc.proc.exit_code
                except sh.ErrorReturnCode as e:
                    exit_code = e.exit_code
                alive = f'dead[{exit_code}]'
            ping  = sup.commander.ping()
            last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)
            table.add_row(
                Text(pre)+Text(node.name),
                Text(f"{node.state} - {alive}", style=('bold red' if node.is_error() else "")),
                sup.desc.host,
                str(alive),
                str(ping),
                Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                str(sup.last_ok_command)
            )

        else:
            table.add_row(Text(pre)+Text(node.name),
                          Text(f"{node.state}", style=('bold red' if node.is_error() else "")))

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
