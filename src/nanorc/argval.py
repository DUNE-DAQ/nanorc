

def validate_path_exists(prompted_path):
    if not path.exists(prompted_path):
        raise RuntimeError(f"Couldn't find {prompted_path} in filesystem")
    return prompted_path


def validate_timeout(ctx, param, timeout):
    if timeout is None:
        return timeout
    if timeout<=0:
        raise click.BadParameter('Timeout should be >0')
    return timeout

def validate_node_path(ctx, param, prompted_path):

    if prompted_path is None:
        return None

    if prompted_path[0] != '/':
        prompted_path = '/'+prompted_path

    hierarchy = prompted_path.split("/")
    topnode = ctx.obj.rc.topnode

    r = Resolver('name')
    try:
        node = r.get(topnode, prompted_path)
        return node
    except Exception as ex:
        raise click.BadParameter(f"Couldn't find {prompted_path} in the tree") from ex

    return node

def validate_partition_number(ctx, param, number):
    if number<0 or number>10:
        raise click.BadParameter(f"Partition number should be between 0 and 10 (you fed {number})")
    return number
