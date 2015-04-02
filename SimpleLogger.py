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

# Text colors:
# grey
# red
# green
# yellow
# blue
# magenta
# cyan
# white
# 
# Text highlights:
# on_grey
# on_red
# on_green
# on_yellow
# on_blue
# on_magenta
# on_cyan
# on_white
# 
# Attributes:
# bold
# dark
# underline
# blink
# reverse
# concealed
	        
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
    def __init__(self, name="logger",
                       logToStdout=True, stdout=None, 
                       logToFile=True, logFileBasename="log", logFileExtension="log", maxlogFileSize=10):
        # set name
        self.set_name(name)
        # set log to stdout
        self.set_log_to_stdout(logToStdout)
        # set stdout
        self.set_stdout(stdout)
        # set log to file
        self.set_log_to_file(logToFile)
        # set maximum logFile size
        self.set_maximum_log_file_size(maxlogFileSize)
        # set logFile name
        self.set_log_file_extension(logFileExtension)
        # set logFile name
        self.set_log_file_basename(logFileBasename)
        # create levels
        self.__logTypeFileFlags   = {}
        self.__logTypeStdoutFlags = {}
        self.__logTypeNames       = {}
        self.__logTypeLevels      = {}
        self.__logTypeColors      = {}
        self.add_level("debug", name="DEBUG", level=0, stdoutFlag=True, fileFlag=True)
        self.add_level("info", name="INFO", level=10, stdoutFlag=True, fileFlag=True)
        self.add_level("warn", name="WARNING", level=20, stdoutFlag=True, fileFlag=True)
        self.add_level("error", name="ERROR", level=30, stdoutFlag=True, fileFlag=True)
        self.add_level("critical", name="CRITICAL", level=100, stdoutFlag=True, fileFlag=True)
        
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
    def logTypes(self):
        """list of all defined log types"""
        return self.__logTypeNames.keys()
    
    @property
    def logTypeFileFlags(self):
        """dictionary of all defined log types logging file flags"""
        return copy.deepcopy(self.__logTypeFileFlags)
    
    @property
    def logTypeStdoutFlags(self):
        """dictionary of all defined log types logging stdout flags"""
        return copy.deepcopy(self.__logTypeStdoutFlags)
    
    @property
    def logTypeNames(self):
        """dictionary of all defined log types name showing when logging"""
        return copy.deepcopy(self.__logTypeNames)
        
    @property
    def logTypeLevels(self):
        """dictionary of all defined log types levels showing when logging"""
        return copy.deepcopy(self.__logTypeLevels)
            
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
    
    def set_stdout(self, stream=None):
        if stream is None:
            self.__stdout = sys.stdout
        else:
            assert hasattr(stream, 'read') and hasattr(stream, 'write'), "stdout stream is not valid"
            self.__stdout = stream
        # set stdout colors
        if self.__stream_allow_colours(self.__stdout):
            colors = ["black","red","green","yellow","blue","magenta","white"]
            self.__textAttr              = dict( [(colors[idx],"") for idx in range(8)] )
            self.__textAttr["end"]       = "" 
            self.__textAttr["bold"]      = "" 
            self.__textAttr["underline"] = "" 
        else:
            names  = ["black","red","green","yellow","blue","magenta","white"]
            colors = ["\x1b[1;%dm"%(30+c) for c in range(8)]
            self.__textAttr              = dict( [(names[idx],colors[idx]) for idx in range(len(names))] )
            self.__textAttr["end"]       = "\x1b[0m" 
            self.__textAttr["bold"]      = "\x1b[1m" 
            self.__textAttr["underline"] = "\x1b[4m" 

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
    
    def set_minimum_level(self, level, stdoutFlag=True, fileFlag=True):
        # check level
        if level is None:
            level = 0
        assert is_number(level), "level must be a number"
        level = float(level)
        # check flags
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        # set levels
        for logType, l in self.__logTypeLevels.items():
            if stdoutFlag:
                self.__logTypeStdoutFlags[logType] = l>=level
            if fileFlag:
                self.__logTypeFileFlags[logType] = l>=level
                
    def set_maximum_level(self, level, stdoutFlag=True, fileFlag=True):
        # check level
        if level is None:
            level = 0
        assert is_number(level), "level must be a number"
        level = float(level)
        # check flags
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        # set levels
        for logType, l in self.__logTypeLevels.items():
            if stdoutFlag:
                self.__logTypeStdoutFlags[logType] = l<level
            if fileFlag:
                self.__logTypeFileFlags[logType] = l<level
    
    def set_log_type_stdout_flag(self, logType, flag):
         assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
         assert isinstance(flag, bool), "flag must be boolean"
         self.__logTypeStdoutFlags[logType] = flag
    
    def set_log_type_file_flag(self, logType, flag):
         assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
         assert isinstance(flag, bool), "flag must be boolean"
         self.__logTypeFileFlags[logType] = flag
    
    def set_log_type_name(self, logType, name):
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        self.__logTypeNames[logType] = name
    
    def set_log_type_level(self, logType, level):
        assert is_number(level), "level must be a number"
        level = float(level)
        name = str(name)
        self.__logTypeLevels[logType] = level
        
    def add_level(self, logType, name=None, level=0, stdoutFlag=True, fileFlag=True):
        # check logType
        assert logType not in self.__logTypeStdoutFlags.keys(), "logType '%s' already defined" %logType
        assert isinstance(logType, basestring), "logType must be a string"
        logType=str(logType)
        # check name
        if name is None:
            name = logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        # check level
        assert is_number(level), "level must be a number"
        level = float(level)
        # check flags
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        # add logType
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag
        self.__logTypeNames[logType]       = name
        self.__logTypeLevels[logType]      = level
                
    def format_message(self, level, message):
        header = self.get_header(level, message)
        footer = self.get_footer(level, message)
        return "%s%s%s\n" %(header, message, footer)

    def get_header(self, level, message):
        dateTime = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        return "%s - %s <%s> "%(dateTime, self.__name, self.__logTypeNames[level])
        
    def get_footer(self, level, message):
        return ""
        
    def __log_to_file(self, message):
        if os.path.isfile(self.__logFileName):
            if os.stat(self.__logFileName).st_size/1e6 < self.__maxlogFileSize:
                self.set_log_file_name()
        fd = open(self.__logFileName, 'a')
        fd.write(message)
        fd.close()
        
    def __log_to_stdout(self, message):
        self.__stdout.write(message)
    
    def log(self, level, message):
        # log to stdout
        if self.__logToStdout and self.__logTypeStdoutFlags[level]:
            log = self.format_message(level, message)
            self.__log_to_stdout(log)
        # log to file
        if self.__logToFile and self.__logTypeFileFlags[level]:
            log = self.format_message(level, message)
            self.__log_to_file(log)
        

if __name__ == "__main__":
    l=Logger("fullrmc")
    l.set_log_to_file(True)
    l.add_level("step accepted", name="info")
    l.add_level("step rejected", name="info")
    for logType in l.logTypes:
        l.log(logType, "this is '%s' level log message."%logType)
    
    
    #from ctypes import *
    #STD_OUTPUT_HANDLE_ID = c_ulong(0xfffffff5)
    #windll.Kernel32.GetStdHandle.restype = c_ulong
    #std_output_hdl = windll.Kernel32.GetStdHandle(STD_OUTPUT_HANDLE_ID)
    #for color in xrange(16):
    #    windll.Kernel32.SetConsoleTextAttribute(std_output_hdl, color)
    #    print "hello"
    #    
