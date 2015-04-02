#!/usr/bin/python
import os 
import sys
from datetime import datetime
#import timeit

#print datetime.now()
#print timeit.timeit("datetime.now()", setup="from __main__ import datetime", number=1000)/1000
#print datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
#print timeit.timeit("datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')", setup="from __main__ import datetime", number=1000)/1000
#exit()


def is_number(number):
    """
    check if number is convertible to float.
    
    :Parameters:
        #. number (str, number): input number
                   
    :Returns:
        #. result (bool): True if convertible, False otherwise
    """
    if isinstance(number, (int, long, float, complex)):
        return True
    try:
        float(number)
    except:
        return False
    else:
        return True
    
class logger(object):
    def __init__(self, logToTerminal=True, logToFile=True, 
                       logFileBasename="log", logFileExtension="log", maxlogFileSize=10,
                       formater=None):
        # set log to terminal
        self.set_log_to_terminal(logToTerminal)
        # set log to file
        self.set_log_to_file(logToFile)
        # set maximum logFile size
        self.set_maximum_log_file_size(maxlogFileSize)
        # set logFile name
        self.set_log_file_extension(logFileExtension)
        # set logFile name
        self.set_log_file_basename(logFileBasename)
        # set formater
        self.set_formater(formater)
        
    
    @property
    def logToTerminal(self):
        return self.__logToTerminal
    
    @property
    def logToFile(self):
        return self.__logToFile
    
    @property
    def logFileName(self):
        return self.__logFileBasename
            
    @property
    def logFileBasename(self):
        return self.__logFileBasename
        
    @property
    def logFileExtension(self):
        return self.__logFileExtension
        
    @property
    def maxlogFileSize(self):
        return self.__maxlogFileSize
    
    def _get_time_string(self, format='%Y-%m-%d %H:%M:%S'):
        return datetime.strftime(datetime.now(), format)
            
    def set_log_to_terminal(self, logToTerminal):
        self.__logToTerminal = logToTerminal
    
    def set_log_to_file(self, logToFile):
        assert isinstance(logToFile, basestring), "logToFile must be a basestring"
        logToFile = str(logToFile)
        assert len(logToFile), "logToFile can't be empty"
        assert logToFile[-1] != ".", "logToFile last character can't be a dot"
        self.__logToFile = logToFile
    
    def set_log_file_extension(self, logFileExtension):
        assert isinstance(logFileExtension, basestring), "logFileExtension must be a basestring"
        logFileExtension = str(logFileExtension)
        assert len(logFileExtension), "logFileExtension can't be empty"
        assert logToFile[0] != ".", "logFileExtension first character can't be a dot"
        assert logToFile[-1] != ".", "logFileExtension last character can't be a dot"
        self.__logFileExtension = logFileExtension
    
    def set_log_file_basename(self, logFileBasename):
        assert isinstance(logFileBasename, basestring), "logFileBasename must be a basestring"
        logFileBasename = str(logFileBasename)
        self.__logFileBasename = logFileBasename
        # create log file name
        self.__logFileName = self.__logFileBasename+"."+self.__logFileExtension
        number = 0
        while os.path.isfile(self.__logFileName):
            if os.stat(self.__logFileName).st_size/1e6 < self.__maxlogFileSize:
                break
            number += 1
            self.__logFileName = self.__logFileBasename+"_"+str(number)+"."+self.__logFileExtension
    
    def set_maximum_log_file_size(self, maxlogFileSize):
        assert is_number(maxlogFileSize), "maxlogFileSize must be a number"
        maxlogFileSize = float(maxlogFileSize)
        assert maxlogFileSize>=1, "maxlogFileSize minimum size is 1 megabytes"
        self.__maxlogFileSize = maxlogFileSize
        



import timeit
def create_fake_log(fname):
    fd = open(fname, 'a')
    fd.write("a"*100+"\n")
    fd.close()
    

fname = 'log.txt'

# empty
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()",  number=10000)/10000.
#print os.stat('log.txt').st_size/1e6

#  first try
print timeit.timeit("create_fake_log(fname)",setup="from __main__ import fname, create_fake_log",  number=1000)/1000.
#create_fake_log(fname)    
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()", number=10000)/10000.

#create_fake_log(fname)    
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()", number=10000)/10000.

#create_fake_log(fname)    
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()", number=10000)/10000.

#create_fake_log(fname)    
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()", number=10000)/10000.

#create_fake_log(fname)    
#print timeit.timeit("fd = open('log.txt', 'a')\nfd.close()", number=10000)/10000.
#print os.stat('log.txt').st_size/1e6
