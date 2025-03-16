# uncompyle6 version 3.9.1
# Python bytecode version base 2.7 (62211)
# Decompiled from: Python 2.7.12 (v2.7.12:d33e0cf91556, Jun 27 2016, 15:19:22) [MSC v.1500 32 bit (Intel)]
# Embedded file name: im\RoomController.pyo
# Compiled at: 2022-05-10 20:52:12
from imvu.task.Future import Future
import logging, imvu.scene
from imvu.task import task, Return, ActiveObject, activemethod, NamedTaskCollection
import imvu.product
from imvu.util import assertInRelease
from imvu.event import EventSink
import weakref
logger = logging.getLogger('imvu.' + __name__)

class RoomController(ActiveObject, EventSink):

    def __init__(self, roomModel, userAccount, productLoader, serviceProvider, parentWindow, session, roomOwners=[], isAlwaysDriver=False):
        ActiveObject.__init__(self, serviceProvider.taskScheduler)
        EventSink.__init__(self, serviceProvider.eventBus)
        self.__disposed = False
        self.__roomModel = roomModel
        self.__userAccount = userAccount
        self.__productLoader = productLoader
        self.__serviceProvider = serviceProvider
        self.__roomLoadFailed = False
        self.__roomState = None
        self.__roomOwnerId = 0
        self.__roomPid = 0
        self.__roomInstanceId = ''
        self.__hasNotSentRoomState = True
        self.__serviceProvider.eventBus.register(self.__roomModel, 'setFurnitureState', self.__furniStateChanged)
        self.__serviceProvider.eventBus.register(session, 'ControlMessage', self.__controlMessageListener)
        self.__totalNumSlotsToConfigure = 0
        self.__lastStarServerRepr = None
        self.__slotsFailedAuth = set()
        self.__furniFailedAuth = set()
        self.__undoUserInterfaceController = None
        self.__pendingRoomState = None
        self.__undo = []
        self.__redo = []
        self.__undoActive = False
        self.__furniLoadingTasks = NamedTaskCollection(self.__serviceProvider.taskScheduler)
        self.__parentWindow = parentWindow
        self.__roomOwners = roomOwners
        self.__isAlwaysDriver = isAlwaysDriver
        self.__isDriver = True
        return

    def __repr__(self):
        return '<RoomController cid:%r pid:%r>' % (self.ownerId, self.roomPid)

    @activemethod
    def __furniStateChanged(self, event):
        self.__isDriver = True
        info = event.info
        slotId = info['slotId']
        loadFailed = yield self.__roomState.loadFailed()
        furniState = yield self.__roomState.getFurnitureState(slotId)
        if not furniState and not loadFailed:
            newState = self.__roomModel.getFurnitureState(slotId)
            if newState:
                self.__roomState.setFurnitureState(slotId, newState)

    def isLockedRoomBodyPattern(self):
        return self.roomPid and self.__roomModel.getProductId() == self.roomPid and self.__roomModel.getProductInstance().isLockedRoom()

    def _getRoomStateContentsForTest(self):
        return self.__serviceProvider.taskScheduler._wait(self.__roomState.getRoomContents())

    @property
    def room(self):
        return self.__roomModel

    @property
    def roomState(self):
        return self.__roomState

    @property
    def ownerId(self):
        return self.__roomOwnerId

    @ownerId.setter
    def ownerId(self, newOwner):
        self.__roomOwnerId = newOwner
        if self.__roomState:
            self.__roomState.setOwnerId(newOwner)

    @property
    def roomPid(self):
        return self.__roomModel.getProductId()

    @property
    def roomInstanceId(self):
        return self.__roomInstanceId

    @property
    def userAccount(self):
        return self.__userAccount

    @activemethod
    def __roomStateChanged(self, event):
        self.__isDriver = True
        self.__updateFurniture()
        self.__serviceProvider.eventBus.fire(self, 'RoomStateChanged', {'reason': (event.info['reason'])})

    def isDriver(self):
        return self.__isDriver

    @activemethod
    def __updateFurniture(self):
        self.__roomLoadFailed = yield self.__roomState.loadFailed()
        if self.__roomLoadFailed:
            yield Return()
        self.__roomOwnerId = yield self.__roomState.getOwnerId()
        self.__roomPid = yield self.__roomState.getRoomProductId()
        self.__roomInstanceId = yield self.__roomState.getInstanceId()

        @task
        def loadProduct(productId, slotId, state, properties):
            if self.__disposed:
                yield Return(None)
            if productId in self.__furniFailedAuth:
                self.__slotsFailedAuth.add(slotId)
                self.__onFurnitureError(slotId)
                yield Return(None)
            userIds = [
             self.ownerId] + self.__roomOwners
            productInstance = None
            for userId in userIds:
                try:
                    productInstance = yield self.__productLoader.createProductInstance(userId, productId)
                except imvu.product.ProductAuthorizationError as e:
                    logger.info('createProductInstance(%r, %r, False) failed with ProductAuthorizationError', userId, productId, exc_info=True)
                except imvu.product.ProductLoadError as e:
                    logger.info('createProductInstance(%r, %r, False) failed with ProductLoadError %r', userId, productId, e)
                    if e.isTransient:
                        self.__onFurnitureError(slotId)
                        yield Return(None)
                    else:
                        raise
                else:
                    break

            if not productInstance:
                self.__slotsFailedAuth.add(slotId)
                self.__furniFailedAuth.add(productId)
                self.__onFurnitureError(slotId)
                yield Return(None)
            logger.info('__updateFurniture adding slot %d, productId %d', slotId, productId)
            try:
                self.__totalNumSlotsToConfigure += 1
                self.__roomModel.addFurniture(slotId, productInstance, state, properties)
            except imvu.scene.SceneStateException as se:
                logger.exception('RoomController.loadProduct failed to load product %r', productInstance)

            return

        self.__totalNumSlotsToConfigure = 0
        roomStateSlots = yield self.__roomState.getSlots()
        if self.__disposed:
            yield Return(None)
        roomSlots = self.__roomModel.getSlots()
        for slotId in set(roomStateSlots) | set(roomSlots):
            if slotId not in roomStateSlots:
                logger.info(('__updateFurniture removing slot {0}').format(slotId))
                self.__roomModel.removeFurniture(slotId)
            else:
                newProductId = yield self.__roomState.getFurnitureProductId(slotId)
                newState = yield self.__roomState.getFurnitureState(slotId)
                newProperties = yield self.__roomState.getFurnitureProperties(slotId)
                if self.__disposed:
                    yield Return(None)
                oldProductId = None
                oldState = None
                oldProperties = None
                if slotId in roomSlots:
                    oldState = self.__roomModel.getFurnitureState(slotId)
                    oldProductInstance = self.__roomModel.getFurnitureProductInstance(slotId)
                    if oldProductInstance:
                        oldProductId = oldProductInstance.getProductId()
                    oldProperties = self.__roomModel.getFurnitureProperties(slotId)
                if newProductId == oldProductId:
                    if newState != oldState or newProperties != oldProperties:
                        logger.info(('__updateFurniture setting state for slot {0}').format(slotId))
                        self.__roomModel.setFurnitureState(slotId, newState)
                        logger.info(('__updateFurniture setting properties for slot {0}').format(slotId))
                        self.__roomModel.setFurnitureProperties(slotId, newProperties)
                        self.__totalNumSlotsToConfigure += 1
                elif oldProductId:
                    self.__roomModel.removeFurniture(slotId)
                self.__furniLoadingTasks.runTask('load %d %d' % (newProductId, slotId), loadProduct(newProductId, slotId, newState, newProperties))

        return

    def __onFurnitureError(self, slotId):
        self.__serviceProvider.eventBus.fire(self, 'FurnitureLoadError', {'slotId': slotId})

    @activemethod
    def loadRoomState(self, roomState, pi):
        self.__isDriver = True
        assertInRelease(roomState)
        assertInRelease(pi)
        try:
            self.__roomModel.setProductInstance(pi)
        except imvu.scene.SceneStateException as se:
            logger.exception('RoomController.loadRoomState failed to load product %r with SceneStateException %r', pi, se)

        if roomState == self.__roomState:
            assertInRelease(pi.getProductId() == self.__roomPid)
        elif self.__roomState:
            self.unregisterEventListener(self.__roomState, 'RoomStateChanged', self.__roomStateChanged)
        self.__roomState = roomState
        self.registerEventListener(self.__roomState, 'RoomStateChanged', self.__roomStateChanged)
        self.__roomLoadFailed = yield self.__roomState.loadFailed()
        self.__roomPid = yield self.__roomState.getRoomProductId()
        self.__roomOwnerId = yield self.__roomState.getOwnerId()
        self.__roomInstanceId = yield self.__roomState.getInstanceId()
        if not self.__roomLoadFailed:
            exportedState = yield self.__roomState.exportState()
            self.__lastStarServerRepr = self.__roomState.encodeRoomState(exportedState)
            self.__updateFurniture()
            assertInRelease(pi.getProductId() == self.__roomPid)
        logger.info('RoomController.loadRoomState %r:(pid=%r, owner=%r), %r', self.__roomState, self.__roomPid, self.__roomOwnerId, pi)
        if self.__pendingRoomState:
            self.__bringRoomStateCurrent(self.__pendingRoomState)
            self.__pendingRoomState = None
        return

    def isFullyLoaded(self):
        if not self.__roomState:
            return True # Texas change: Changed from False to True
        if self.__roomLoadFailed:
            return False
        if self.__furniLoadingTasks.hasUnfinishedTasks():
            return True # Texas change: Changed from False to True
        return True

    @activemethod
    def removePids(self, pids):
        self.__isDriver = True
        logger.info('removePids: %r', pids)
        num = 0
        if self.__roomState is None:
            yield Return(0)
        contents = yield self.__roomState.getRoomContents()
        for slotId, (furni_pid, furni_state, _) in contents.iteritems():
            if furni_pid in pids:
                self.__roomState.removeFurniture(slotId)
                num += 1

        yield Return(num)
        return

    def __notifyEditRoom(self):
        self.__userAccount.recordFact('Edit room', dict(ownerId=self.ownerId, roomPid=self.roomPid, roomInstanceId=self.roomInstanceId))

    @task
    def __addProduct(self, pid, outfit=[]):
        self.__isDriver = True
        slotId = yield self.__roomState.addFurniture(pid)
        if outfit:
            yield self.__roomState.setFurnitureProperty(slotId, 'outfit', [p.getProductId() for p in outfit])
        newState = yield self.__roomState.getFurnitureState(slotId)
        self.__addUndoHistory('add', slotId, pid, None, newState, None, None, None)
        yield Return(slotId)
        return

    @activemethod
    def useProduct(self, pi):
        self.__isDriver = True
        if self.__roomState is None:
            return
        else:
            if pi.isFurniture():
                yield self.__addProduct(pi.getProductId())
            elif pi.isEnvironment():
                self.__roomModel.setProductInstance(pi)
            else:
                raise imvu.scene.SceneStateException('could not use product %r', pi)
            return

    @activemethod
    def addFurniture(self, productId, outfit=[]):
        self.__isDriver = True
        if self.__roomState == None:
            return
        else:
            if isinstance(productId, Future):
                productId = yield productId
            slotId = yield self.__addProduct(productId, outfit)
            yield Return(slotId)
            return

    @activemethod
    def cloneFurniture(self, slotId):
        self.__isDriver = True
        if self.__roomState == None:
            return
        else:
            pid = yield self.__roomState.getFurnitureProductId(slotId)
            slotId = yield self.__addProduct(pid)
            self.__notifyEditRoom()
            yield Return(slotId)
            return

    @activemethod
    def setFurnitureState(self, slotId, newState):
        self.__isDriver = True
        if self.__roomState == None:
            return
        else:
            if isinstance(slotId, Future):
                slotId = yield slotId
            if isinstance(newState, Future):
                newState = yield newState
            pid = yield self.__roomState.getFurnitureProductId(slotId)
            oldState = yield self.__roomState.getFurnitureState(slotId)
            self.__roomState.setFurnitureState(slotId, newState)
            self.__addUndoHistory('state', slotId, pid, oldState, newState, None, None, None)
            self.__notifyEditRoom()
            return

    @activemethod
    def removeFurniture(self, slotId):
        self.__isDriver = True
        if isinstance(slotId, Future):
            slotId = yield slotId
        oldPid = yield self.__roomState.getFurnitureProductId(slotId)
        oldState = yield self.__roomState.getFurnitureState(slotId)
        self.__roomState.removeFurniture(slotId)
        self.__addUndoHistory('rem', slotId, oldPid, oldState, None, None, None, None)
        self.__notifyEditRoom()
        return

    @activemethod
    def getFurnitureState(self, slot):
        state = yield self.__roomState.getFurnitureState(slot)
        yield Return(state)

    @activemethod
    def getSlots(self):
        slots = yield self.__roomState.getSlots()
        yield Return(slots)

    def getFurnitureProduct(self, slotId):
        return self.__roomModel.getFurnitureProductInstance(slotId)

    def __bringRoomStateCurrent(self, encodedState):
        if not self.__isAlwaysDriver:
            self.__isDriver = False
        if self.__roomState:
            decodedState = self.__roomState.decodeRoomState(encodedState)
            if decodedState:
                self.__roomState.bringStateCurrent(decodedState)
        else:
            self.__pendingRoomState = encodedState

    def bringRoomStateCurrent(self, encodedState):
        self.__bringRoomStateCurrent(encodedState)

    def dispose(self):
        self.__disposed = True
        self.__parentWindow = None
        self.stopAttachedTasks()
        if self.__roomState:
            self.__roomState.stopAttachedTasks()
        return

    @activemethod
    def __localUserCanChangeRoom(self):
        if not self.__userAccount:
            yield Return(True)
        if not self.ownerId:
            yield Return(True)
        if self.__userAccount.getUserId() in self.__roomOwners:
            yield Return(True)
        yield Return(self.ownerId == self.__userAccount.getUserId())

    @task
    def stateAsStarCommands(self):
        if not (yield self.__localUserCanChangeRoom()):
            yield Return([])
        commands = []
        if self.__roomState:
            roomPid = yield self.__roomState.getRoomProductId()
            commands.extend(['*use %d' % roomPid])
            starCommands = yield self.__sendStarCommands()
            commands.extend(starCommands)
        yield Return(commands)

    @activemethod
    def __sendStarCommands(self):
        exported = yield self.__roomState.exportState()
        exported['room_state']['room_info']['revision_id'] = '2'
        encoded = self.__roomState.encodeRoomState(exported)
        if self.__hasNotSentRoomState:
            contents = yield self.__roomState.getRoomContents()
            if len(contents) == 0 or self.__lastStarServerRepr == encoded:
                yield Return([])
        msg = '*imvu:setRoomState ' + encoded
        logger.debug('sending star command msg: %r', msg)
        self.__lastStarServerRepr = encoded
        self.__hasNotSentRoomState = False
        yield Return([msg])

    @property
    def slotsFailedAuth(self):
        return self.__slotsFailedAuth

    def getTotalNumSlotsToConfigure(self):
        return max(self.__totalNumSlotsToConfigure, len(self.room.getRoomContents().keys()))

    @activemethod
    def clearUndoStack(self):
        self.__undo = []
        self.__redo = []
        self.__undoActive = False

    def setUndoUserInterfaceController(self, controller):
        self.__undoUserInterfaceController = weakref.ref(controller)

    class UndoActivationContext:
        pass

    @activemethod
    def __activateUndo(self):
        assertInRelease(not self.__undoActive)
        self.__undo.insert(0, [])
        self.__undoActive = True

    @activemethod
    def __deactivateUndo(self):
        if self.__undo[0] == []:
            self.__undo = self.__undo[1:]
        self.__undoActive = False

    def undoActivated(self):

        def enter():
            self.__activateUndo()

        def exit(type, value, traceback):
            self.__deactivateUndo()

        result = self.UndoActivationContext()
        result.__enter__ = enter
        result.__exit__ = exit
        return result

    def __addUndoHistory(self, type, slotId, pid, oldState, newState, property, oldValue, newValue):
        if self.__undoActive == False:
            return
        else:
            self.__undo[0].insert(0, [type, slotId, pid, oldState, newState, property, oldValue, newValue])
            self.__purgeRedoStack(slotId)
            self.__notifyUndoStateChange(None, type, [slotId], oldState, newState)
            return

    def __purgeRedoStack(self, slotId):
        newRedo = []
        for changes in self.__redo:
            newChanges = []
            for change in changes:
                if change[1] != slotId:
                    newChanges.append(change)

            if newChanges != []:
                newRedo.append(newChanges)

        self.__redo = newRedo

    @activemethod
    def undoFurnitureChange(self, slotId=None):
        self.__isDriver = True
        assertInRelease(self.__undoActive == False)
        if isinstance(slotId, Future):
            slotId = yield slotId
        i = self.__locateMatch(self.__undo, slotId)
        if i < 0:
            return
        self.__redo.insert(0, [])
        while len(self.__undo[i]) > 0:
            change = self.__undo[i].pop(0)
            type, slotId, pid, oldState, newState, property, oldValue, newValue = change
            if type == 'add':
                if newState == '':
                    newState = yield self.__roomState.getFurnitureState(slotId)
                    change[4] = newState
                self.__roomState.removeFurniture(slotId)
            elif type == 'state':
                yield self.__roomState.setFurnitureState(slotId, oldState)
            elif type == 'rem':
                newSlotId = yield self.__roomState.addFurniture(pid, oldState)
                self.__renumberHistory(self.__undo, slotId, newSlotId)
                change[1] = newSlotId
            elif type == 'prop':
                self.__roomState.setFurnitureProperty(slotId, property, oldValue)
            self.__redo[0].append(change)
            self.__notifyUndoStateChange('undo', type, [slotId], newState, oldState)

        self.__undo.pop(i)
        if self.__redo[0] == []:
            self.__redo.pop(0)

    @activemethod
    def redoFurnitureChange(self, slotId=None):
        self.__isDriver = True
        assertInRelease(self.__undoActive == False)
        if isinstance(slotId, Future):
            slotId = yield slotId
        i = self.__locateMatch(self.__redo, slotId)
        if i < 0:
            return
        self.__undo.insert(0, [])
        while len(self.__redo[i]) > 0:
            change = self.__redo[i].pop()
            type, slotId, pid, oldState, newState, property, oldValue, newValue = change
            if type == 'add':
                newSlotId = yield self.__roomState.addFurniture(pid, newState)
                self.__renumberHistory(self.__redo, slotId, newSlotId)
                change[1] = newSlotId
            elif type == 'state':
                yield self.__roomState.setFurnitureState(slotId, newState)
            elif type == 'rem':
                yield self.__roomState.removeFurniture(slotId)
            elif type == 'prop':
                self.__roomState.setFurnitureProperty(slotId, property, newValue)
            self.__undo[0].insert(0, change)
            self.__notifyUndoStateChange('redo', type, [slotId], oldState, newState)

        self.__redo.pop(i)
        if self.__undo[0] == []:
            self.__undo.pop(0)

    def __renumberHistory(self, stack, oldSlotId, newSlotId):
        for changes in stack:
            for change in changes:
                if change[1] == oldSlotId:
                    change[1] = newSlotId

    def __notifyUndoStateChange(self, fromStack, type, slotIds, furniStateBefore, furniStateAfter):
        if self.__undoUserInterfaceController:
            undoUIController = self.__undoUserInterfaceController()
            if undoUIController:
                for slotId in slotIds:
                    undoIsAvailable = self.__locateMatch(self.__undo, slotId) >= 0
                    redoIsAvailable = self.__locateMatch(self.__redo, slotId) >= 0
                    undoUIController.notifyUndoStateChange(fromStack, type, slotId, furniStateBefore, furniStateAfter, undoIsAvailable, redoIsAvailable)

    def __locateMatch(self, stack, slotId):
        for i, changes in enumerate(stack):
            for change in changes:
                if slotId is None or (change[0] == 'state' or change[0] == 'prop') and change[1] == slotId:
                    return i

        return -1

    @activemethod
    def getFurnitureProperty(self, slotId, name):
        returnValue = yield self.__roomState.getFurnitureProperty(slotId, name)
        yield Return(returnValue)

    @activemethod
    def setFurnitureProperty(self, slotId, name, value):
        self.__isDriver = True
        oldValue = yield self.__roomState.getFurnitureProperty(slotId, name)
        if value != oldValue:
            self.__roomState.setFurnitureProperty(slotId, name, value)
            self.__addUndoHistory('prop', slotId, None, None, None, name, oldValue, value)
        return

    def __controlMessageListener(self, event):
        if event.info.get('command') == 'SetRoomState':
            self.bringRoomStateCurrent(event.info['state'])
