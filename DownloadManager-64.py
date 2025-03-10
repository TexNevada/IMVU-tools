# uncompyle6 version 3.9.1
# Python bytecode version base 2.7 (62211)
# Decompiled from: Python 2.7.12 (v2.7.12:d33e0cf91556, Jun 27 2016, 15:19:22) [MSC v.1500 32 bit (Intel)]
# Embedded file name: imvu\http\DownloadManager.pyo
# Compiled at: 2022-05-10 20:52:14
import logging, weakref, imvu.weakmethod
from imvu.task import Future, GetPriority, PriorityQueue, Return, TaskOwner, task
logger = logging.getLogger('imvu.' + __name__)

class UnthrottledDownloadManager(object):

    def __init__(self, network):
        self.__network = network

    @task
    def getUrlContents(self, url, headers={}):
        data = yield self.__network.getUrlContents(url, headers)
        if isinstance(data, tuple):
            data = data[0]
        yield Return(data)


class DownloadManager(TaskOwner):
    MAX_CONCURRENT_REQUESTS = 64

    def __init__(self, taskScheduler, network):
        TaskOwner.__init__(self, taskScheduler)
        self.__network = network
        self.__requestQueue = PriorityQueue()
        for i in range(self.MAX_CONCURRENT_REQUESTS):
            self.attachTask(self.__downloadWorker())

    @task
    def __downloadWorker(self):
        while True:
            future_wr, url, headers = yield self.__requestQueue.get()
            future = future_wr()
            if future is None:
                continue
            try:
                data = yield self.__network.getUrlContents(url, headers)
                if isinstance(data, tuple):
                    data = data[0]
            except imvu.network.networkExceptions as e:
                logger.exception('Error downloading request %s', url)
                future.complete(None, e)
            else:
                logger.info('Downloaded request %s', url)
                future.complete(data, None)
                del data

        return

    @task
    def getUrlContents(self, url, headers={}):
        myPriority = yield GetPriority()
        future = Future()
        self.__requestQueue.put((weakref.ref(future), url, headers), priority=myPriority)
        yield Return((yield future))
