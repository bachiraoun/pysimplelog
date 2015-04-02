#!/usr/bin/python
import os 
import sys
import copy
from datetime import datetime
#import timeit

#print datetime.now()
#print timeit.timeit("datetime.now()", setup="from __main__ import datetime", number=1000)/1000
#print datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
#print timeit.timeit("datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')", setup="from __main__ import datetime", number=1000)/1000
#exit()

# http://code.activestate.com/recipes/475116/
# https://github.com/dgentry/Todo-o-matic/blob/master/gcolors.py
# http://blog.mathieu-leplatre.info/colored-output-in-console-with-python.html
# https://github.com/ilovecode1/pyfancy/blob/master/pyfancy.py

	        
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
    
class Logger(object):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = ["\x1b[1;%dm"%(30+c) for c in range(8)]
    END = "\x1b[0m"
    
    
    def __init__(self, name="logger",
                       logToStdout=True, logToFile=True, 
                       logFileBasename="log", logFileExtension="log", maxlogFileSize=10):
        # set name
        self.set_name(name)
        # set log to stdout
        self.set_log_to_stdout(logToStdout)
        # set log to file
        self.set_log_to_file(logToFile)
        # set maximum logFile size
        self.set_maximum_log_file_size(maxlogFileSize)
        # set logFile name
        self.set_log_file_extension(logFileExtension)
        # set logFile name
        self.set_log_file_basename(logFileBasename)
        # create levels
        self.__levelsFileFlags   = {}
        self.__levelsStdoutFlags = {}
        self.__levelsName        = {}
        self.__levelsColors      = {}
        self.add_level("info", name=None, color=None, stdoutFlag=True, fileFlag=True)
        self.add_level("warn", name=None, color=None, stdoutFlag=True, fileFlag=True)
        self.add_level("error", name=None, color=None, stdoutFlag=True, fileFlag=True)
        self.add_level("critical", name=None, color=None, stdoutFlag=True, fileFlag=True)
        # set stdout color allowed flag
        self.__stdoutColorAllowed = self.__has_colours(sys.stdout)

    
    def __stream_allow_colours(self, stream):
        """
        following from Python cookbook, #475186
        check whether a stream allows coloring
        """
        if not hasattr(stream, "isatty"):
            return False
        if not stream.isatty():
            return False # auto color only on TTYs
        try:
            import curses
            curses.setupterm()
            return curses.tigetnum("colors") > 2
        except:
            # guess false in case of error
            return False
            
    @property
    def levels(self):
        """list of all defined levels"""
        return self.__levelsName.keys()
    
    @property
    def levelsFileFlags(self):
        """dictionary of all defined levels logging file flags"""
        return copy.deepcopy(self.__levelsFileFlags)
    
    @property
    def levelsStdoutFlags(self):
        """dictionary of all defined levels logging stdout flags"""
        return copy.deepcopy(self.__levelsStdoutFlags)
    
    @property
    def levelsName(self):
        """dictionary of all defined levels name showing when logging"""
        return copy.deepcopy(self.__levelsName)
            
    @property
    def name(self):
        """logger name."""
        return self.__name
        
    @property
    def logToStdout(self):
        """log to stdout flag."""
        return self.__logToStdout
    
    @property
    def logToFile(self):
        """log to file flag."""
        return self.__logToFile
    
    @property
    def logFileName(self):
        """currently used log file name."""
        return self.__logFileName
            
    @property
    def logFileBasename(self):
        """log file basename."""
        return self.__logFileBasename
        
    @property
    def logFileExtension(self):
        """log file extension."""
        return self.__logFileExtension
        
    @property
    def maxlogFileSize(self):
        """maximum allowed logfile size in megabytes."""
        return self.__maxlogFileSize
        
    def set_name(self, name):
        assert isinstance(name, basestring), "name must be a string"
        self.__name = name
               
    def set_log_to_stdout(self, logToStdout):
        assert isinstance(logToStdout, bool), "logToStdout must be boolean"
        self.__logToStdout = logToStdout
    
    def set_log_to_file(self, logToFile):
        assert isinstance(logToFile, bool), "logToFile must be boolean"
        self.__logToFile = logToFile
    
    def set_log_file_extension(self, logFileExtension):
        assert isinstance(logFileExtension, basestring), "logFileExtension must be a basestring"
        logFileExtension = str(logFileExtension)
        assert len(logFileExtension), "logFileExtension can't be empty"
        assert logFileExtension[0] != ".", "logFileExtension first character can't be a dot"
        assert logFileExtension[-1] != ".", "logFileExtension last character can't be a dot"
        self.__logFileExtension = logFileExtension
    
    def set_log_file_basename(self, logFileBasename):
        assert isinstance(logFileBasename, basestring), "logFileBasename must be a basestring"
        logFileBasename = str(logFileBasename)
        self.__logFileBasename = logFileBasename
        # set log file name
        self.set_log_file_name()
    
    def set_log_file_name(self):
        """Automatically set logFileName attribute"""
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
        
    def add_level(self, level, name=None, stdoutFlag=True, fileFlag=True):
        assert level not in self.__levelsStdoutFlags.keys(), "level '%s' already defined" %level
        assert isinstance(level, basestring), "level must be a string"
        level=str(level)
        if name is None:
            name = level
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        # add level
        self.__levelsStdoutFlags[level] = stdoutFlag
        self.__levelsFileFlags[level] = fileFlag
        self.__levelsName[level]  = name
                
    def formatter(self, level, message, stdoutFormat=True):
        dateTime = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        return "%s - %s <%s> %s" %(dateTime, self.__name, self.__levelsName[level], message)
        
    def log(self, level, message):
        # log to stdout
        if self.__logToStdout:
            if self.__levelsStdoutFlags[level]:
                log = self.formatter(level, message, stdoutFormat=True)
                print log
        # log to file
        if self.__logToFile:
            if self.__levelsFileFlags[level]:
                log = self.formatter(level, message, stdoutFormat=False)
                print log
        

if __name__ == "__main__":
    l=Logger("fullrmc")
    l.set_log_to_file(False)
    l.add_level("step accepted", name="info")
    l.add_level("step rejected", name="info")
    for level in l.levels:
        l.log(level, "this is '%s' level log message."%level)
    
    
    
    
    
