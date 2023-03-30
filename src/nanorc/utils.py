import threading
import queue
import time

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