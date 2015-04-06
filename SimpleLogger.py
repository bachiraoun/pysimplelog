# python standard distribution imports
import os 
import sys
import copy
from datetime import datetime
import atexit

	        
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
        # initialize types parameters
        self.__logTypeFileFlags   = {}
        self.__logTypeStdoutFlags = {}
        self.__logTypeNames       = {}
        self.__logTypeLevels      = {}
        self.__logTypeFormat      = {}
        # create default types
        self.add_type("debug", name="DEBUG", level=0, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_type("info", name="INFO", level=10, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_type("warn", name="WARNING", level=20, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_type("error", name="ERROR", level=30, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_type("critical", name="CRITICAL", level=100, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        # flush at python exit
        atexit.register(self._flush_atexit_logfile)  
        
    def __stream_format_allowed(self, stream):
        """
        Check whether a stream allows formatting such as coloring.
        Inspired from Python cookbook, #475186
        """
        # curses isn't available on all platforms
        try:
            import curses as CURSES
        except:
            CURSES = None
        if CURSES is not None:
            CURSES.setupterm()
            return CURSES.tigetnum("colors") >= 2
        else:
            # guess false in case of error
            return False
        # if stream is not TeleTYpewriter (tty)
        if not hasattr(stream, "isatty"):
            return False
        if not stream.isatty():
            return False # auto color only on TTYs
        else:
            return True
            
    def _flush_atexit_logfile(self):   
        if self.__logFileStream is not None:
           self.__logFileStream.close() 
          
    @property
    def logTypes(self):
        """list of all defined log types"""
        return self.__logTypeNames.keys()
    
    @property
    def logLevels(self):
        """dictionary of all defined log types levels"""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFileFlags(self):
        """dictionary of all defined log types logging to a file flags"""
        return copy.deepcopy(self.__logTypeFileFlags)
    
    @property
    def logTypeStdoutFlags(self):
        """dictionary of all defined log types logging to stdout flags"""
        return copy.deepcopy(self.__logTypeStdoutFlags)
    
    @property
    def logTypeNames(self):
        """dictionary of all defined log types logging names"""
        return copy.deepcopy(self.__logTypeNames)
        
    @property
    def logTypeLevels(self):
        """dictionary of all defined log types levels showing when logging"""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFormats(self):
        """dictionary of all defined log types format showing when logging"""
        return copy.deepcopy(self.__logTypeFormats)
        
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
        self.__stdoutFontFormat = self.set_fonts_attributes(stream)
    
    def set_fonts_attributes(self, stream):
        # foreground color
        fgNames = ["black","red","green","orange","blue","magenta","cyan","grey"]
        fgCode  = [str(idx) for idx in range(30,38,1)]
        fgNames.extend(["dark grey","light red","light green","yellow","light blue","pink","light cyan"])
        fgCode.extend([str(idx) for idx in range(90,97,1)])
        # background color
        bgNames = ["black","red","green","orange","blue","magenta","cyan","grey"]
        bgCode  = [str(idx) for idx in range(40,48,1)]
        # attributes
        attrNames = ["bold","underline","blink","invisible","strike through"]
        attrCode  = ["1","4","5","8","9"]
        # set reset
        resetCode = "0"
        # if attributing is not allowed
        if not self.__stream_format_allowed(stream):
            fgCode    = ["" for idx in fgCode]
            bgCode    = ["" for idx in bgCode]
            attrCode  = ["" for idx in attrCode]
            resetCode = ""
        # set font attributes dict
        color = dict( [(fgNames[idx],fgCode[idx]) for idx in range(len(fgCode))] )
        highlight = dict( [(bgNames[idx],bgCode[idx]) for idx in range(len(bgCode))] )
        attributes = dict( [(attrNames[idx],attrCode[idx]) for idx in range(len(attrCode))] )
        return {"color":color, "highlight":highlight, "attributes":attributes, "reset":resetCode}
    
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
        # create log file stram
        self.__logFileStream = None
        
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
        
    def add_type(self, logType, name=None, level=0, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None):
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
        # set wrapFancy
        wrapFancy=["",""]
        if color is not None:
            assert color in self.__stdoutFontFormat["color"], "color %s not known"%str(color)
            code = self.__stdoutFontFormat["color"][color]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if highlight is not None:
            assert highlight in self.__stdoutFontFormat["highlight"], "highlight %s not known"%str(highlight)
            code = self.__stdoutFontFormat["highlight"][highlight]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if attributes is None:
            attributes = []
        elif isinstance(attributes, basestring):
            attributes = [str(attributes)]
        for attr in attributes:
            assert attr in self.__stdoutFontFormat["attributes"], "attribute %s not known"%str(attr)
            code = self.__stdoutFontFormat["attributes"][attr]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if len(wrapFancy[0]):
            wrapFancy = ["\033["+self.__stdoutFontFormat["reset"]+wrapFancy[0]+"m" , "\033["+self.__stdoutFontFormat["reset"]+"m" ]               
        # add logType
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag
        self.__logTypeNames[logType]       = name
        self.__logTypeLevels[logType]      = level
        self.__logTypeFormat[logType]      = wrapFancy
                
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
        # create log file stream
        if self.__logFileStream is None:
            self.__logFileStream = open(self.__logFileName, 'a')
        elif self.__logFileStream.tell()/1e6 > self.__maxlogFileSize:
            self.set_log_file_name()
            self.__logFileStream = open(self.__logFileName, 'a')
        # log to file    
        self.__logFileStream.write(message)
        
    def __log_to_stdout(self, message):
        self.__stdout.write(message)
    
    def log(self, level, message):
        # log to stdout
        if self.__logToStdout and self.__logTypeStdoutFlags[level]:
            log = self.format_message(level, message)
            log = self.__logTypeFormat[level][0] + log[:-2] + self.__logTypeFormat[level][1] + "\n"
            self.__log_to_stdout(log)
        # log to file
        if self.__logToFile and self.__logTypeFileFlags[level]:
            log = self.format_message(level, message)
            self.__log_to_file(log)
            
    def info(self, message):
        """alias to message at information level"""
        self.log("info", message)
    
    def information(self, message):
        """alias to message at information level"""
        self.log("info", message)
        
    def warn(self, message):
        """alias to message at warning level"""
        self.log("warn", message)
    
    def warning(self, message):
        """alias to message at warning level"""
        self.log("warn", message)
        
    def error(self, message):
        """alias to message at error level"""
        self.log("error", message)
        
    def critical(self, message):
        """alias to message at critical level"""
        self.log("critical", message)
        
    def debug(self, message):
        """alias to message at debug level"""
        self.log("debug", message)
    
        
if __name__ == "__main__":
    import time
    l=Logger("log test")
    l.set_log_to_file(True)
    l.add_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
    l.add_type("wrong", name="info", color='magenta', attributes=["strike through"])
    l.add_type("important", name="info", color='black', highlight="orange", attributes=["bold"])
    for logType in l.logTypes:
        tic = time.clock()
        l.log(logType, "this is '%s' level log message."%logType)
        print "%s seconds\n"%str(time.clock()-tic)
    
