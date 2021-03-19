#!/usr/bin/env python3

import click
import click_shell

@click_shell.shell(prompt='dummy>')
def dummy():
    pass

@dummy.command()
def cmd1():
    pass


if __name__ == '__main__':
    dummy()