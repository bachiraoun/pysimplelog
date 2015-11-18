"""
Usage
=====
.. code-block:: python
        
        # import Logger
        from simplelog import Logger
        
        # initialize
        l=Logger("log test")
        
        # Add new log types.
        l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
        l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
        l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold","blink"])
        
        # test logging
        l.info("I am info, called using my shortcut method")
        l.log("info", "I am  info, called using log method")
        
        l.warn("I am warn, called using my shortcut method")
        l.log("warn", "I am warn, called using log method")
        
        l.error("I am error, called using my shortcut method")
        l.log("error", "I am error, called using log method")
        
        l.critical("I am critical, called using my shortcut method")
        l.log("critical", "I critical, called using log method")
        
        l.debug("I am debug, called using my shortcut method")
        l.log("debug", "I am debug, called using log method")
        
        l.log("super critical", "I am super critical, called using log method because I have no shortcut method.")
        l.log("wrong", "I am wrong, called using log method because I have no shortcut method.")
        l.log("important", "I am important, called using log method because I have no shortcut method.")
        
        
output
====== 
.. code-block:: python
      
        2015-11-18 11:40:44 - log test <INFO> I am info, called using my shortcut method
        2015-11-18 11:40:44 - log test <INFO> I am  info, called using log method
        2015-11-18 11:40:44 - log test <WARNING> I am warn, called using my shortcut method
        2015-11-18 11:40:44 - log test <WARNING> I am warn, called using log method
        2015-11-18 11:40:44 - log test <ERROR> I am error, called using my shortcut method
        2015-11-18 11:40:44 - log test <ERROR> I am error, called using log method
        2015-11-18 11:40:44 - log test <CRITICAL> I am critical, called using my shortcut method
        2015-11-18 11:40:44 - log test <CRITICAL> I critical, called using log method
        2015-11-18 11:40:44 - log test <DEBUG> I am debug, called using my shortcut method
        2015-11-18 11:40:44 - log test <DEBUG> I am debug, called using log method
        2015-11-18 11:40:44 - log test <SUPER CRITICAL> I am super critical, called using log method because I have no shortcut method.
        2015-11-18 11:40:44 - log test <info> I am wrong, called using log method because I have no shortcut method.
        2015-11-18 11:40:44 - log test <info> I am important, called using log method because I have no shortcut method.

"""
# python standard distribution imports
import os 
import sys
import copy
from datetime import datetime
import atexit

        	        
def _is_number(number):
    if isinstance(number, (int, long, float, complex)):
        return True
    try:
        float(number)
    except:
        return False
    else:
        return True
    
class Logger(object):
    """ 
    This is simplelog main Logger class definition.\n  
    
    A logging is constituted of a header a message and a footer.
    In the current implementation the footer is empty and the header is as the following:\n
    date time - loggerName <logTypeName>\n
    
    In order to change any of the header or the footer, '_get_header' and '_get_footer'
    methods must be overloaded.
    
    :Parameters:
       #. name (str): The logger name.
       #. flush (boolean): Whether to always flush the logging streams.
       #. logToStdout (boolean): Whether to log to the standard output stream.
       #. stdout (None, stream): The standard output stream. If None, system standard
          output will be set automatically. Otherwise any stream with read and write 
          methods can be passed
       #. logToFile (boolean): Whether to log to to file.
       #. logFileBasename (str): Logging file basename. A logging file full name is 
          set as logFileBasename.logFileExtension
       #. logFileExtension (str): Logging file extension. A logging file full name is 
          set as logFileBasename.logFileExtension
       #. logFileMaxSize (number): The maximum size in Megabytes of a logging file. 
          Once exceeded, another logging file as logFileBasename_N.logFileExtension
          will be created. Where N is an automatically incremented number.
    """
    def __init__(self, name="logger", flush=True,
                       logToStdout=True, stdout=None, 
                       logToFile=True, logFileBasename="log", logFileExtension="log", logFileMaxSize=10):
        # set name
        self.set_name(name)
        # set flush
        self.set_flush(flush)
        # set log to stdout
        self.set_log_to_stdout_flag(logToStdout)
        # set stdout
        self.set_stdout(stdout)
        # set log to file
        self.set_log_to_file_flag(logToFile)
        # set maximum logFile size
        self.set_log_file_maximum_size(logFileMaxSize)
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
        self.add_log_type("debug", name="DEBUG", level=0, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_log_type("info", name="INFO", level=10, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_log_type("warn", name="WARNING", level=20, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_log_type("error", name="ERROR", level=30, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
        self.add_log_type("critical", name="CRITICAL", level=100, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None)
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
    def flush(self):
        """Flush flag"""
        return self.__flush
        
    @property
    def logTypes(self):
        """list of all defined log types"""
        return self.__logTypeNames.keys()
    
    @property
    def logLevels(self):
        """dictionary copy of all defined log types levels"""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFileFlags(self):
        """dictionary copy of all defined log types logging to a file flags"""
        return copy.deepcopy(self.__logTypeFileFlags)
    
    @property
    def logTypeStdoutFlags(self):
        """dictionary copy of all defined log types logging to stdout flags"""
        return copy.deepcopy(self.__logTypeStdoutFlags)
    
    @property
    def logTypeNames(self):
        """dictionary copy of all defined log types logging names"""
        return copy.deepcopy(self.__logTypeNames)
        
    @property
    def logTypeLevels(self):
        """dictionary copy of all defined log types levels showing when logging"""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFormats(self):
        """dictionary copy of all defined log types format showing when logging"""
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
    def logFileMaxSize(self):
        """maximum allowed logfile size in megabytes."""
        return self.__maxlogFileSize
        
    def set_name(self, name):
        """ 
        Set the logger name. 
    
        :Parameters:
           #. name (str): The logger name.
        """
        assert isinstance(name, basestring), "name must be a string"
        self.__name = name
    
    def set_flush(self, flush):
        """ 
        Set the logger flush flag
    
        :Parameters:
           #. flush (boolean): Whether to always flush the logging streams.
        """
        assert isinstance(flush, bool), "flush must be boolean"
        self.__flush = flush
        
    def set_stdout(self, stream=None):
        """ 
        Set the logger standard output stream.
    
        :Parameters:
           #. stdout (None, stream): The standard output stream. If None, system standard
              output will be set automatically. Otherwise any stream with read and write 
              methods can be passed
        """
        if stream is None:
            self.__stdout = sys.stdout
        else:
            assert hasattr(stream, 'read') and hasattr(stream, 'write'), "stdout stream is not valid"
            self.__stdout = stream
        # set stdout colors
        self.__stdoutFontFormat = self.__get_stream_fonts_attributes(stream)
    
    def __get_stream_fonts_attributes(self, stream):
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
    
    def set_log_to_stdout_flag(self, logToStdout):
        """ 
        Set the logging to the defined standard output flag.
    
        :Parameters:
           #. logToStdout (boolean): Whether to log to the standard output stream.
        """
        assert isinstance(logToStdout, bool), "logToStdout must be boolean"
        self.__logToStdout = logToStdout
    
    def set_log_to_file_flag(self, logToFile):
        """ 
        Set the logging to a file flag.
    
        :Parameters:
           #. logToFile (boolean): Whether to log to to file.
        """
        assert isinstance(logToFile, bool), "logToFile must be boolean"
        self.__logToFile = logToFile
    
    def set_log_type_flags(self, logType, stdoutFlag, fileFlag):
        """ 
        Set a defined log type flags.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. stdoutFlag (boolean): Whether to log to the standard output stream.
           #. fileFlag (boolean): Whether to log to to file.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag       
       
    def set_log_file_extension(self, logFileExtension):
        """ 
        Set the log file extension.
    
        :Parameters:
           #. logFileExtension (str): Logging file extension. A logging file full name is 
              set as logFileBasename.logFileExtension
        """
        assert isinstance(logFileExtension, basestring), "logFileExtension must be a basestring"
        logFileExtension = str(logFileExtension)
        assert len(logFileExtension), "logFileExtension can't be empty"
        assert logFileExtension[0] != ".", "logFileExtension first character can't be a dot"
        assert logFileExtension[-1] != ".", "logFileExtension last character can't be a dot"
        self.__logFileExtension = logFileExtension
    
    def set_log_file_basename(self, logFileBasename):
        """ 
        Set the log file basename.
    
        :Parameters:
           #. logFileBasename (str): Logging file basename. A logging file full name is 
              set as logFileBasename.logFileExtension
        """
        assert isinstance(logFileBasename, basestring), "logFileBasename must be a basestring"
        logFileBasename = str(logFileBasename)
        self.__logFileBasename = logFileBasename
        # set log file name
        self.__set_log_file_name()
    
    def __set_log_file_name(self):
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
        
    def set_log_file_maximum_size(self, logFileMaxSize):
        """ 
        Set the log file maximum size in megabytes
    
        :Parameters:
           #. logFileMaxSize (number): The maximum size in Megabytes of a logging file. 
              Once exceeded, another logging file as logFileBasename_N.logFileExtension
              will be created. Where N is an automatically incremented number.
        """
        assert _is_number(logFileMaxSize), "logFileMaxSize must be a number"
        logFileMaxSize = float(logFileMaxSize)
        assert logFileMaxSize>=1, "logFileMaxSize minimum size is 1 megabytes"
        self.__maxlogFileSize = logFileMaxSize
    
    def set_minimum_level(self, level=0, stdoutFlag=True, fileFlag=True):
        """ 
        Set the minimum logging level. All levels below the minimum will be ignored at logging.
    
        :Parameters:
           #. level (number): The minimum level of logging.
           #. stdoutFlag (boolean): Whether to apply this minimum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this minimum level to file logging.
        """
        # check level
        if level is None:
            level = 0
        assert _is_number(level), "level must be a number"
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
                
    def set_maximum_level(self, level=0, stdoutFlag=True, fileFlag=True):
        """ 
        Set the maximum logging level. All levels above the maximum will be ignored at logging.
    
        :Parameters:
           #. level (number): The maximum level of logging.
           #. stdoutFlag (boolean): Whether to apply this maximum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this maximum level to file logging.
        """
        # check level
        if level is None:
            level = 0
        assert _is_number(level), "level must be a number"
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
        """ 
        Set a logtype standard output logging flag.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. flag (boolean): The standard output logging flag.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(flag, bool), "flag must be boolean"
        self.__logTypeStdoutFlags[logType] = flag
    
    def set_log_type_file_flag(self, logType, flag):
        """ 
        Set a logtype file logging flag.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. flag (boolean): The file logging flag.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(flag, bool), "flag must be boolean"
        self.__logTypeFileFlags[logType] = flag
    
    def set_log_type_name(self, logType, name):
        """ 
        Set a logtype name.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. name (str): The logtype new name.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        self.__logTypeNames[logType] = name
    
    def set_log_type_level(self, logType, level):
        """ 
        Set a logtype logging level.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. level (number): The level of logging.
        """
        assert _is_number(level), "level must be a number"
        level = float(level)
        name = str(name)
        self.__logTypeLevels[logType] = level
        
    def add_log_type(self, logType, name=None, level=0, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None):
        """ 
        Add a new logtype.
    
        :Parameters:
           #. logType (str): The logtype.
           #. name (None, str): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (boolean): The standard output logging flag.
           #. fileFlag (boolean): The file logging flag.
           #. color (None, str): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey , 
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, str): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, str): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through
        
        **N.B** *logging color, highlight and attributes are not allowed on all types of streams.*
        """
        # check logType
        assert logType not in self.__logTypeStdoutFlags.keys(), "logType '%s' already defined" %logType
        assert isinstance(logType, basestring), "logType must be a string"
        logType=str(logType)
        # set log type
        self.__set_log_type(logType=logType, name=name, level=level, 
                            stdoutFlag=stdoutFlag, fileFlag=fileFlag, 
                            color=color, highlight=highlight, attributes=attributes)
        
                
    def __set_log_type(self, logType, name=None, level=0, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None):
        # check name
        if name is None:
            name = logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        # check level
        assert _is_number(level), "level must be a number"
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
    
    def update_log_type(self, logType, name=None, level=None, stdoutFlag=True, fileFlag=True, color=None, highlight=None, attributes=None):
        """ 
        update a logtype.
    
        :Parameters:
           #. logType (str): The logtype.
           #. name (None, str): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (boolean): The standard output logging flag.
           #. fileFlag (boolean): The file logging flag.
           #. color (None, str): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey , 
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, str): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, str): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through
        
        **N.B** *logging color, highlight and attributes are not allowed on all types of streams.*
        """
        # check logType
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' is not defined" %logType
        # update log type
        self.__set_log_type(logType=logType, name=name, level=level, 
                            stdoutFlag=stdoutFlag, fileFlag=fileFlag, 
                            color=color, highlight=highlight, attributes=attributes)
        
        
        
    def _format_message(self, level, message):
        header = self._get_header(level, message)
        footer = self._get_footer(level, message)
        return "%s%s%s" %(header, message, footer)

    def _get_header(self, level, message):
        dateTime = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        return "%s - %s <%s> "%(dateTime, self.__name, self.__logTypeNames[level])
        
    def _get_footer(self, level, message):
        return ""
        
    def __log_to_file(self, message):
        # create log file stream
        if self.__logFileStream is None:
            self.__logFileStream = open(self.__logFileName, 'a')
        elif self.__logFileStream.tell()/1e6 > self.__maxlogFileSize:
            self.__set_log_file_name()
            self.__logFileStream = open(self.__logFileName, 'a')
        # log to file    
        self.__logFileStream.write(message)
        
    def __log_to_stdout(self, message):
        self.__stdout.write(message)
    
    def log(self, logType, message):
        """ 
        log a message of a certain logtype.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. message (str): Any message to log.
        """
        # log to stdout
        if self.__logToStdout and self.__logTypeStdoutFlags[logType]:
            log = self._format_message(logType, message)
            log = self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n"
            self.__log_to_stdout(log)
            if self.__flush:self.__stdout.flush()
        # log to file
        if self.__logToFile and self.__logTypeFileFlags[logType]:
            log = self._format_message(logType, message)
            self.__log_to_file(log+"\n")
            if self.__flush:self.__logFileStream.flush()
    
    def force_log(self, logType, message, stdout=True, file=True):
        """ 
        Force logging a message of a certain logtype whether logtype level is allowed or not.
    
        :Parameters:
           #. logType (str): A defined logging type.
           #. message (str): Any message to log.
           #. stdout (boolean): Whether to force logging to standard output.
           #. file (boolean): Whether to force logging to file.
        """
        # log to stdout
        if stdout:
            log = self._format_message(logType, message)
            log = self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n"
            self.__log_to_stdout(log)
            self.__stdout.flush()
        if file:    
            # log to file
            log = self._format_message(logType, message)
            self.__log_to_file(log+"\n")
            self.__logFileStream.flush()
            
    def flush(self):
        """Flush all streams."""
        if self.__logFileStream is not None:
            self.__logFileStream.flush()
        if self.__stdout is not None:
            self.__stdout.flush()
        
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
    l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
    l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
    l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold","blink"])
    for logType in l.logTypes:
        tic = time.clock()
        l.log(logType, "this is '%s' level log message."%logType)
        print "%s seconds\n"%str(time.clock()-tic)
        
        

    
