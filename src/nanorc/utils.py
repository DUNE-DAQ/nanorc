import threading
import queue
import time

def strip_env_for_rte(env):
    import copy as cp
    import re
    env_stripped = cp.deepcopy(env)
    for key in env.keys():
        if key in ["PATH","CET_PLUGIN_PATH","DUNEDAQ_SHARE_PATH","LD_LIBRARY_PATH","LIBRARY_PATH","PYTHONPATH"]:
            del env_stripped[key]
        if re.search(".*_SHARE", key) and key in env_stripped:
            del env_stripped[key]
    return env_stripped

def get_version():
    from os import getenv
    version = getenv("DUNE_DAQ_BASE_RELEASE")
    if not version:
        raise RuntimeError('Utils: dunedaq version not in the variable env DUNE_DAQ_BASE_RELEASE! Exit nanorc and\nexport DUNE_DAQ_BASE_RELEASE=dunedaq-vX.XX.XX\n')
    return version

def get_releases_dir():
    from os import getenv
    releases_dir = getenv("SPACK_RELEASES_DIR")
    if not releases_dir:
        raise RuntimeError('Utils: cannot get env SPACK_RELEASES_DIR! Exit nanorc and\nrun dbt-workarea-env or dbt-setup-release.')
    return releases_dir

def release_or_dev():
    from os import getenv
    is_release = getenv("DBT_SETUP_RELEASE_SCRIPT_SOURCED")
    if is_release:
        return 'rel'
    is_devenv = getenv("DBT_WORKAREA_ENV_SCRIPT_SOURCED")
    if is_devenv:
        return 'dev'
    return 'rel'

def get_rte_script():
    from os import path

    ver = get_version()
    releases_dir = get_releases_dir()

    script = path.join(releases_dir, ver, 'daq_app_rte.sh')

    if not path.exists(script):
        raise RuntimeError(f'Couldn\'t understand where to find the rte script tentative: {script}')

    return script




class Task:
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

class TaskEnqueuerThread(threading.Thread):
    def __init__(self, obj):
        super().__init__()
        self.obj = obj
        self.running = True
        self.queue = queue.Queue()

    def enqueue_asynchronous(self, task):
        if not self.running:
            raise Exception('Thread is stopping, cannot enqueue more tasks')
        self.queue.put(task)

    def enqueue_synchronous(self, task):
        if not self.running:
            raise Exception('Thread is not stopping, cannot enqueue more tasks')
        try:
            self.queue.join()
        except queue.Empty:
            pass
        self.queue.put(task)
        self.queue.join()

    def stop(self):
        self.running = False

    def abort(self):
        self.running = False
        self.queue.queue.clear()

    def run(self):
        while self.running or self.queue.qsize()>0:
            try:
                task = self.queue.get(block=False, timeout=0.1)
                getattr(self.obj, task.function)(*task.args, **task.kwargs)
                self.queue.task_done()
            except queue.Empty:
                #print('Queue empty, waiting for new tasks...')
                pass
            except Exception as e:
                print(f'Couldn\'t execute the function {task.function} on the object, reason: {str(e)}')
                raise e

            time.sleep(0.1)


def main():
    class some_object():
        def __init__(self, name):
            self.name = name
            print(f'Created object {name}')

        def do_work_1(self, argument):
            print(f'[obj] Doing work 1, {argument}')
            time.sleep(1)
            print(f'[obj] Done work 1, {argument}')

        def do_work_2(self):
            print('[obj] Doing work 2')
            time.sleep(1)
            print('[obj] Done work 2')

    obj = some_object('test')
    tet = TaskEnqueuerThread(obj)
    tet.start()

    print('[main] starting an async task')
    tet.enqueue_asynchronous(Task('do_work_1', 'async test'))
    print('[main] returning directly')
    time.sleep(1.5) # wait for the async task to finish
    print('[main] starting a sync task')
    tet.enqueue_synchronous (Task('do_work_1', 'sync test'))
    print('[main] returning after work 1')
    print('[main] starting an async task')
    tet.enqueue_asynchronous(Task('do_work_2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async1'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    print('[main] returning directly, now adding a synchronous task, will wait before being executed')
    tet.enqueue_synchronous (Task('do_work_1', 'sync'))
    print('[main] returning after everything is done')

    tet.enqueue_asynchronous(Task('do_work_2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async1'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    print('[main] sending stopping')
    tet.stop()
    print('[main] stopped')
    try:
        tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    except Exception as e:
        print(f'Exception: {str(e)}')

    tet.join()
    print('[main] returning after everything is done')

if __name__ == '__main__':
    print('main')
    main()