"""Single bounded worker. Callbacks are delivered only by the Tk/main thread."""

from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue


class UiWorker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transmi-data")
        self.completed = Queue()
        self.pending = {}
        self.generations = {}
        self.callbacks = {}
        self.closed = False

    def invalidate(self, key):
        self.callbacks.pop((key, self.generations.get(key)), None)
        self.generations[key] = self.generations.get(key, 0) + 1
        future = self.pending.pop(key, None)
        if future:
            future.cancel()

    def submit(self, key, operation, callback):
        if self.closed:
            return
        self.invalidate(key)
        generation = self.generations[key]
        self.callbacks[(key, generation)] = callback
        future = self.executor.submit(operation)
        self.pending[key] = future
        future.add_done_callback(lambda item: self.completed.put((key, generation, item)))

    def drain(self):
        while True:
            try:
                key, generation, future = self.completed.get_nowait()
            except Empty:
                return
            if self.closed or generation != self.generations.get(key):
                continue
            self.pending.pop(key, None)
            callback = self.callbacks.pop((key, generation), None)
            if callback is None:
                continue
            if future.cancelled():
                continue
            try:
                value = future.result()
            except Exception:
                # Never expose exception repr/traceback, which may contain user secrets.
                callback(
                    None,
                    "La operación local falló. Revise los datos o la disponibilidad del archivo.",
                )
            else:
                callback(value, None)

    def close(self):
        self.closed = True
        self.callbacks.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
