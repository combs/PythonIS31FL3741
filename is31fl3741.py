from __future__ import print_function

from .constants import *
from smbus2 import SMBus, i2c_msg
import time

class IS31FL3741DeviceNotFound(IOError):
    pass

class IS31FL3741(object):

    address = 0x30
    busnum = 8
    softwareshutdown = 0
    currentPage = PAGE_LEDPWM1
    enabledOutputs = 9
    logicLevelHigh = True
    pixels = [[0] * 39 for i in range(9)]
    triggerShortDetection = 1
    triggerOpenDetection = 1
    DEBUG = False
    lastDebug = ""
    name = "IS31FL3741"
    scalingDefault = 255

    def debug(self, *args):
        if self.DEBUG:
            if not hasattr(self, "lastDebug"):
                self.lastDebug = ""
            if self.lastDebug != args:
                print(self.name + ":", *args)
            self.lastDebug = args

    def __del__(self):
        # self.smbus.close()
        pass

    def __init__(self, *args, **kwargs):

        # Flags

        if type (args) is not None:
          for arg in args:
              setattr(self,arg,True)

        # key=value parameters

        if type (kwargs) is not None:
          for key, value in kwargs.items():
              if type(value) is dict:
                  if getattr(self,key):
                        tempdict = getattr(self,key).copy()
                        tempdict.update(value)
                        value = tempdict
              setattr(self,key,value)

        self.smbus = SMBus(self.busnum)

        try:
            self.attemptDetection()
        except IOError:
            raise IS31FL3741DeviceNotFound('Could not communicate with device.')
        except TypeError:
            raise IS31FL3741DeviceNotFound('Device detection failed.')

        self.reset()
        self.setContrast(255)
        self.triggerOpenShortDetection = True
        self.setConfiguration()
        self.debug("Initialized.")

    def attemptDetection(self):

        # REGISTER_INTERRUPT_STATUS defaults to 0, can only be 0-3
        if self.read(REGISTER_INTERRUPT_STATUS) > 3:
            raise TypeError('REGISTER_INTERRUPT_STATUS is an invalid value--is this IS31FL3741?')

        # after any other command the write lock register should reset to 0
        if self.read(REGISTER_COMMAND_WRITE_LOCK) != 0:
            raise TypeError('REGISTER_COMMAND_WRITE_LOCK was not 0--is this IS31FL3741?')

        # 0xC0 is not a readable address in any of the registers
        # It doesn't return a read error, but does always return 0
        if self.read(0xC0) != 0:
            raise TypeError('Was able to read an address that should not be readable (0xC0)--is this IS31FL3741?')

        # It accepts writes but returns 0 afterwards.
        # So if this does otherwise, it's an EEPROM or something
        try:
            if self.read(0xC0) != 0:
                self.write(0xC0, 0) # restore previous 0 value in case it matters
                raise TypeError('Was able to write/read an address that should not be readable (0xC0)--is this IS31FL3741?')

        except IOError:
            # all's well.
            pass

        # later IS31FL37xx devices support this...
        self.selectPage(PAGE_FUNCTION)
        try:
            idregister=self.read(REGISTER_ID)
            if idregister != self.address * 2:
                raise TypeError('ID register value',idregister,'does not match IS31FL3741 value:',self.address)
        except IOError:
            # all's well.
            pass


        self.debug("IS31FL3741 device detected.")
        return True

    def selectPage(self,value):
        if self.currentPage is not value:
            self.debug("changing page to",value,"from",self.currentPage)
            self.write(REGISTER_COMMAND_WRITE_LOCK,VALUE_WRITE_LOCK_DISABLE_ONCE)
            self.write(REGISTER_COMMAND,value)
            self.currentPage = value

    def setContrast(self,value):
        self.selectPage(PAGE_FUNCTION)
        self.write(REGISTER_FUNCTION_CURRENT_CONTROL,value)

    def reset(self):
        self.selectPage(PAGE_FUNCTION)
        self.currentPage = PAGE_FUNCTION
        self.write(REGISTER_FUNCTION_RESET,VALUE_FUNCTION_RESET)
        self.setAllPixelsScaling([self.scalingDefault] * REGISTER_LEDSCALING_LENGTH)
        self.debug("Controller reset. Scaling reset to",self.scalingDefault)


    def setPixelPWM(self,row,col,val,immediate=True):
        pixel = row*39 + col
        self.pixels[row][col] = val
        # self.debug(row*16,col,"=",row*16 + col)
        page = PAGE_LEDPWM1
        address = pixel
        if address > REGISTER_LEDPWM_LENGTH:
            raise ValueError("Pixel row/col value is beyond allowable max")
        if address > REGISTER_LEDPWM1_END:
            page = PAGE_LEDPWM2
            address -= (REGISTER_LEDPWM1_END + 1)

        if immediate:
            self.selectPage(page)
            self.write(address,val)

    def setAllPixelsPWM(self,values):
        desiredLength = REGISTER_LEDPWM_LENGTH
        if len(values) != desiredLength:
            raise ValueError("Received wrong length for setAllPixelsPWM: " + str(len(values)) + ", wanted " + str(desiredLength))

        # so the desired register structure in IS31FL3741 is, uh, unusual
        #
        # for each row, pixels 0-29 are in Page 1 if row < 6; else Page 2
        # and pixels 30-38 are always in Page 2
        # 
        # row 0: page 0, addresses 0:29 ... and page 1, addresses 90:98
        # row 1: page 0, addresses 30:59 ...    page 1, addresses 99:107
        # ...
        # row 6: page 1, addresses 0:29     and page 1, addresses 144:152
        # row 7: page 1, addresses 0:59         page 1, addresses 153:161

        pageOne, pageTwo = [0] * 256, [0] * 256
        for i in range(6):
            pageOne[i*30:(i+1)*30] = values[ 39 * i : 39 * i + 30]
        for i in range(6,9):
            pageTwo[(i-6)*30:(i-5)*30] = values[ 39 * i : 39 * i + 30]
        for i in range(9):
            pageTwo[90:171] = values[ 39 * i + 30 : 39 * (i + 1) ] 

        # pageOne = values[REGISTER_LEDPWM1_START:REGISTER_LEDPWM1_END+1]
        # pageTwo = values[REGISTER_LEDPWM1_END+1:REGISTER_LEDPWM1_END+1+REGISTER_LEDPWM2_END+1]


        self.selectPage(PAGE_LEDPWM1)
        iterator = 0
        messages = []
        for chunk in self.chunks(pageOne,32):
            chunk.insert(0, iterator * 32)
            messages.append(i2c_msg.write(self.address, chunk))
            iterator += 1
        self.smbus.i2c_rdwr(*messages)

        self.selectPage(PAGE_LEDPWM2)
        messages = []
        iterator = 0
        for chunk in self.chunks(pageTwo,32):
            chunk.insert(0, iterator * 32)
            messages.append(i2c_msg.write(self.address, chunk))
            
            iterator += 1
        self.smbus.i2c_rdwr(*messages)


    def setAllPixelsScaling(self,values):
        desiredLength = REGISTER_LEDSCALING_LENGTH
        if len(values) != desiredLength:
            raise ValueError("Received wrong length for setAllPixelsScaling: " + str(len(values)) + ", wanted " + str(desiredLength))
        pageOne = values[REGISTER_LEDSCALING1_START:REGISTER_LEDSCALING1_END+1]
        pageTwo = values[REGISTER_LEDSCALING1_END+1:REGISTER_LEDSCALING1_END+1+REGISTER_LEDSCALING2_END+1]

        iter = 0
        self.selectPage(PAGE_LEDSCALING1)
        messages = []
        for chunk in self.chunks(pageOne,32):
            # self.writeBlock(iter*32,chunk)
            # dest = [iter * 32, *chunk]
            chunk.insert(0, iter * 32)
            messages.append(i2c_msg.write(self.address, chunk))
            iter += 1
        self.smbus.i2c_rdwr(*messages)

        iter = 0
        self.selectPage(PAGE_LEDSCALING2)
        messages = []
        for chunk in self.chunks(pageTwo,32):
            # self.writeBlock(iter*32,chunk)
            # dest = [iter * 32, *chunk]
            chunk.insert(0, iter * 32)
            messages.append(i2c_msg.write(self.address, chunk))
            iter += 1
        self.smbus.i2c_rdwr(*messages)

    def setConfiguration(self):
        self.selectPage(PAGE_FUNCTION)

        regvalue = ( (not self.softwareshutdown) * VALUE_FUNCTION_CONFIGURATION_SSD_SOFTWARE_SHUTDOWN)
        regvalue |= (self.triggerShortDetection * VALUE_FUNCTION_CONFIGURATION_OSDE_SHORT_DETECTION)
        regvalue |= (self.triggerOpenDetection * VALUE_FUNCTION_CONFIGURATION_OSDE_OPEN_DETECTION)
        regvalue |= (self.logicLevelHigh * VALUE_FUNCTION_CONFIGURATION_LGC_HIGH_LOGIC_LEVEL)
        regvalue |= (VALUE_FUNCTION_CONFIGURATION_SWS_OUTPUTS[self.enabledOutputs])

        self.triggerShortDetection = False
        self.triggerOpenDetection = False
        self.write(REGISTER_FUNCTION_CONFIGURATION, regvalue)

    def write(self,register,value):
        self.smbus.write_byte_data(self.address,register,value)

    def writeBlock(self,register,value):
        self.smbus.write_i2c_block_data(self.address,register,value)

    def read(self,register):
        return self.smbus.read_byte_data(self.address,register)
        
    def getOpenPixels(self):
        self.triggerOpenDetection = 1
        self.setConfiguration()
        time.sleep(0.01)
        self.selectPage(PAGE_FUNCTION)
        returners = []
        for i in range(REGISTER_FUNCTION_OPEN_SHORT_START, REGISTER_FUNCTION_OPEN_SHORT_END + 1): # python range not inclusive
            returners.append(self.read(i))
        return returners

    def getShortPixels(self):
        self.triggerShortDetection = 1
        self.setConfiguration()
        time.sleep(0.01)
        self.selectPage(PAGE_FUNCTION)
        returners = []
        for i in range(REGISTER_FUNCTION_OPEN_SHORT_START, REGISTER_FUNCTION_OPEN_SHORT_END + 1): # python range not inclusive
            returners.append(self.read(i))
        return returners

    def chunks(self, values, length):
        for i in range(0, len(values), length):
            yield values[i:i + length]

    def writeBuffer(self):
        flat_list = [item for sublist in self.pixels for item in sublist]
        self.setAllPixelsPWM(0,flat_list)



if __name__ == '__main__':
    for address in range(0x30,0x34):
        print("trying",address)
        try:
            matrix = IS31FL3741(address=address, busnum=8, DEBUG=True, enabledOutputs=9)
            time.sleep(2)
            print("powering on all pixels via PWM register")
            matrix.setAllPixelsPWM([255]*REGISTER_LEDPWM_LENGTH)
            time.sleep(2)
            print("powering off all pixels via PWM register")
            matrix.setAllPixelsPWM([0]*REGISTER_LEDPWM_LENGTH)

            time.sleep(2)

            print("let's fade up from 0 to 10 on all pixels")
            for value in range(10):
                matrix.setAllPixelsPWM([value]*REGISTER_LEDPWM_LENGTH)

            print ("let's draw some rows and cols")
            for row in range(9):
                for col in range(39):
                    matrix.setPixelPWM(row,col, 2)

            print("let's set some arbitrary pixels (check for adjacent shorts)")
            for i in range(9):
                matrix.setPixelPWM(i,i,40)
            for i in range(9):
                matrix.setPixelPWM(8-i,i,20)
            matrix.setPixelPWM(0,0,100)
            matrix.setPixelPWM(0,5,100)
            matrix.setPixelPWM(1,6,100)
            # matrix.setPixelPWM(0,10,100)
            # matrix.setPixelPWM(11,11,100)
            # matrix.setPixelPWM(11,11,100)
            # matrix.setPixelPWM(6,11,100)
            # matrix.setPixelPWM(3,12,3)
            time.sleep(1);
            print("all that done, now let's check for missing/short pixels.")
            print("missing pixels")
            print(matrix.getOpenPixels())
            print("short pixels")
            print(matrix.getShortPixels())
        except Exception as e:
            print("Address",address,"error:",e)
            time.sleep(0.1)
