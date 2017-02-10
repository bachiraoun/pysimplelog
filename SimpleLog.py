"""  
Usage
=====
    .. code-block:: python
            
        # import Logger
        from pysimplelog import Logger
        
        # initialize
        l=Logger("log test")
        
        # change log file basename from simplelog to mylog
        l.set_log_file_basename("mylog")
        
        # change log file extension from .log to .pylog
        l.set_log_file_extension("pylog")
        
        # Add new log types.
        l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
        l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
        l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold"])
        
        # update error log type
        l.update_log_type(logType='error', color='pink', attributes=['underline','bold'])
        
        # print logger
        print l, '\\n'
        
        # test logging
        l.info("I am info, called using my shortcut method.")
        l.log("info", "I am  info, called using log method.")
        
        l.warn("I am warn, called using my shortcut method.")
        l.log("warn", "I am warn, called using log method.")
        
        l.error("I am error, called using my shortcut method.")
        l.log("error", "I am error, called using log method.")
        
        l.critical("I am critical, called using my shortcut method.")
        l.log("critical", "I am critical, called using log method.")
        
        l.debug("I am debug, called using my shortcut method.")
        l.log("debug", "I am debug, called using log method.")
        
        l.log("super critical", "I am super critical, called using log method because I have no shortcut method.")
        l.log("wrong", "I am wrong, called using log method because I have no shortcut method.")
        l.log("important", "I am important, called using log method because I have no shortcut method.")
        
        # print last logged messages
        print "Last logged messages are:
        print "========================="
        print l.lastLoggedMessage
        print l.lastLoggedDebug
        print l.lastLoggedInfo
        print l.lastLoggedWarning
        print l.lastLoggedError
        print l.lastLoggedCritical

                
output
====== 
.. raw:: html 
    
        <body>
        <pre>
        
            Logger (Version %AUTO_VERSION)
            log type       |log name       |level     |std flag  |file flag |
            ---------------|---------------|----------|----------|----------|
            wrong          |info           |0.0       |True      |True      |
            debug          |DEBUG          |0.0       |True      |True      |
            important      |info           |0.0       |True      |True      |
            info           |INFO           |10.0      |True      |True      |
            warn           |WARNING        |20.0      |True      |True      |
            error          |ERROR          |30.0      |True      |True      |
            critical       |CRITICAL       |100.0     |True      |True      |
            super critical |SUPER CRITICAL |200.0     |True      |True      |
            
            2015-11-18 14:25:08 - log test &#60INFO&#62 I am info, called using my shortcut method.
            2015-11-18 14:25:08 - log test &#60INFO&#62 I am  info, called using log method.
            2015-11-18 14:25:08 - log test &#60WARNING&#62 I am warn, called using my shortcut method.
            2015-11-18 14:25:08 - log test &#60WARNING&#62 I am warn, called using log method.
            <font color="pink"><b><ins>2015-11-18 14:25:08 - log test &#60ERROR&#62 I am error, called using my shortcut method.</ins></b></font>
            <font color="pink"><b><ins>2015-11-18 14:25:08 - log test &#60ERROR&#62 I am error, called using log method.</ins></b></font>
            2015-11-18 14:25:08 - log test &#60CRITICAL&#62 I am critical, called using my shortcut method.
            2015-11-18 14:25:08 - log test &#60CRITICAL&#62 I critical, called using log method.
            2015-11-18 14:25:08 - log test &#60DEBUG&#62 I am debug, called using my shortcut method.
            2015-11-18 14:25:08 - log test &#60DEBUG&#62 I am debug, called using log method.
            <font color="red"><b><ins>2015-11-18 14:25:08 - log test &#60SUPER CRITICAL&#62 I am super critical, called using log method because I have no shortcut method.</ins></b></font>
            <font color="magenta"><del>2015-11-18 14:25:08 - log test &#60info&#62 I am wrong, called using log method because I have no shortcut method.</del></font>
            <style>mark{background-color: orange}</style><mark><b>2015-11-18 14:25:08 - log test &#60info&#62 I am important, called using log method because I have no shortcut method.</b></mark>
            
            Last logged messages are:
            =========================
            I am important, called using log method because I have no shortcut method.
            I am debug, called using log method.
            I am  info, called using log method.
            I am warn, called using log method.
            I am error, called using log method.
            I am critical, called using log method.

        </pre>
        <body>
            
"""
# python standard distribution imports
import os 
import sys
import copy
from datetime import datetime
import atexit

# python version dependant imports
if sys.version_info >= (3, 0):
    # This is python 3
    str = str
    long = int
    unicode = str
    bytes = bytes
    basestring = (str,bytes)
else:
    str = str
    unicode = unicode
    bytes = str
    long = long
    basestring = basestring

# import pysimplelog version
try:
    from __pkginfo__ import __version__
except:
    from .__pkginfo__ import __version__

    
# useful definitions    	        
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
       #. name (string): The logger name.
       #. flush (boolean): Whether to always flush the logging streams.
       #. logToStdout (boolean): Whether to log to the standard output stream.
       #. stdout (None, stream): The standard output stream. If None, system standard
          output will be set automatically. Otherwise any stream with read and write 
          methods can be passed
       #. logToFile (boolean): Whether to log to to file.
       #. logFile (None, string): the full log file path including directory basename and 
          extension.  If this is given, all of logFileBasename and logFileExtension 
          will be discarded. logfile is equivalent to logFileBasename.logFileExtension
       #. logFileBasename (string): Logging file directory path and file basename. 
          A logging file full name is set as logFileBasename.logFileExtension
       #. logFileExtension (string): Logging file extension. A logging file full name is 
          set as logFileBasename.logFileExtension
       #. logFileMaxSize (number): The maximum size in Megabytes of a logging file. 
          Once exceeded, another logging file as logFileBasename_N.logFileExtension
          will be created. Where N is an automatically incremented number.
       #. stdoutMinLevel(None, number): The minimum logging to system standard output level.
          If None, standard output minimum level checking is left out.
       #. stdoutMaxLevel(None, number): The maximum logging to system standard output level.
          If None, standard output maximum level checking is left out.
       #. fileMinLevel(None, number): The minimum logging to file level.
          If None, file minimum level checking is left out.
       #. fileMaxLevel(None, number): The maximum logging to file level.
          If None, file maximum level checking is left out.
    """
    def __init__(self, name="logger", flush=True,
                       logToStdout=True, stdout=None, 
                       logToFile=True, logFile=None, logFileBasename="simplelog", logFileExtension="log", logFileMaxSize=10,
                       stdoutMinLevel=None, stdoutMaxLevel=None,
                       fileMinLevel=None, fileMaxLevel=None):
        # set last logged message
        self.__lastLogged = {}
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
        # set logFile basename and extension
        if logFile is not None:
            self.set_log_file(self, logFile)
        else:
            self.__set_log_file_basename(logFileBasename)
            self.set_log_file_extension(logFileExtension)
        # initialize types parameters
        self.__logTypeFileFlags   = {}
        self.__logTypeStdoutFlags = {}
        self.__logTypeNames       = {}
        self.__logTypeLevels      = {}
        self.__logTypeFormat      = {}
        self.__logTypeColor       = {}
        self.__logTypeHighlight   = {}
        self.__logTypeAttributes  = {}
        # initialize forced levels
        self.__forcedStdoutLevels = {}
        self.__forcedFileLevels   = {}
        # set levels
        self.__stdoutMinLevel = None
        self.__stdoutMaxLevel = None
        self.__fileMinLevel   = None
        self.__fileMaxLevel   = None
        self.set_minimum_level(stdoutMinLevel, stdoutFlag=True, fileFlag=False)
        self.set_maximum_level(stdoutMaxLevel, stdoutFlag=True, fileFlag=False)
        self.set_minimum_level(fileMinLevel, stdoutFlag=False, fileFlag=True)
        self.set_maximum_level(fileMaxLevel, stdoutFlag=False, fileFlag=True)
        # create default types
        self.add_log_type("debug", name="DEBUG", level=0, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("info", name="INFO", level=10, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("warn", name="WARNING", level=20, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("error", name="ERROR", level=30, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("critical", name="CRITICAL", level=100, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        # flush at python exit
        atexit.register(self._flush_atexit_logfile)  
        
    def __str__(self):
        string = self.__class__.__name__+" (Version "+str(__version__)+")"
        if not len(self.__logTypeNames):
            string += "\nlog type  |log name  |level     |std flag   |file flag"
            string += "\n----------|----------|----------|-----------|---------"
            return string 
        # get maximum logType and logTypeZName and maxLogLevel
        maxLogType  = max( max([len(k)+1 for k in self.__logTypeNames.keys()]),   len("log type  "))
        maxLogName  = max( max([len(k)+1 for k in self.__logTypeNames.values()]), len("log name  "))
        maxLogLevel = max( max([len(str(k))+1 for k in self.__logTypeLevels.values()]), len("level     "))
        # create header
        string += "\n"+ "log type".ljust(maxLogType) + "|" +\
                        "log name".ljust(maxLogName) + "|" +\
                        "level".ljust(maxLogLevel) + "|" +\
                        "std flag".ljust(10) + "|" +\
                        "file flag".ljust(10) + "|" 
        # create separator
        string += "\n"+ "-"*maxLogType + "|" +\
                        "-"*maxLogName + "|" +\
                        "-"*maxLogLevel + "|" +\
                        "-"*10 + "|" +\
                        "-"*10 + "|" 
        # order from min level to max level
        keys = sorted(self.__logTypeLevels.keys(), key=self.__logTypeLevels.__getitem__)
        # append log types
        for k in keys:
            string += "\n"+ str(k).ljust(maxLogType) + "|" +\
                            str(self.__logTypeNames[k]).ljust(maxLogName) + "|" +\
                            str(self.__logTypeLevels[k]).ljust(maxLogLevel) + "|" +\
                            str(self.__logTypeStdoutFlags[k]).ljust(10) + "|" +\
                            str(self.logTypeFileFlags[k]).ljust(10) + "|" 
        return string
    
    def __stream_format_allowed(self, stream):
        """
        Check whether a stream allows formatting such as coloring.
        Inspired from Python cookbook, #475186
        """
        # curses isn't available on all platforms
        try:
            import curses as CURSES
        except:
            return False
        try:
            CURSES.setupterm()
            return CURSES.tigetnum("colors") >= 2
        except:
            return False
            
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
        
    def _flush_atexit_logfile(self):   
        if self.__logFileStream is not None:
            try:
                self.__logFileStream.flush() 
            except:
                pass
            try:    
                os.fsync(self.__logFileStream.fileno())
            except:
                pass
            self.__logFileStream.close() 

    @property
    def lastLogged(self):
        """Get a dictionary of last logged messages. 
        Keys are log types and values are the the last messages."""
        d = copy.deepcopy(self.__lastLogged)
        d.pop(-1, None)
        return d
        
    @property
    def lastLoggedMessage(self):
        """Get last logged message of any type. Retuns None if no message was logged."""
        return self.__lastLogged.get(-1, None)
    
    @property
    def lastLoggedDebug(self):
        """Get last logged message of type 'debug'. Retuns None if no message was logged."""
        return self.__lastLogged.get('debug', None)

    @property
    def lastLoggedInfo(self):
        """Get last logged message of type 'info'. Retuns None if no message was logged."""
        return self.__lastLogged.get('info', None)

    @property
    def lastLoggedWarning(self):
        """Get last logged message of type 'warn'. Retuns None if no message was logged."""
        return self.__lastLogged.get('warn', None)
                
    @property
    def lastLoggedError(self):
        """Get last logged message of type 'error'. Retuns None if no message was logged."""
        return self.__lastLogged.get('error', None)
        
    @property
    def lastLoggedCritical(self):
        """Get last logged message of type 'critical'. Retuns None if no message was logged."""
        return self.__lastLogged.get('critical', None)
        
    @property
    def flush(self):
        """Flush flag."""
        return self.__flush
        
    @property
    def logTypes(self):
        """list of all defined log types."""
        return self.__logTypeNames.keys()
    
    @property
    def logLevels(self):
        """dictionary copy of all defined log types levels."""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFileFlags(self):
        """dictionary copy of all defined log types logging to a file flags."""
        return copy.deepcopy(self.__logTypeFileFlags)
    
    @property
    def logTypeStdoutFlags(self):
        """dictionary copy of all defined log types logging to Standard output flags."""
        return copy.deepcopy(self.__logTypeStdoutFlags)
    
    @property
    def stdoutMinLevel(self):
        """Standard output minimum logging level."""
        return self.__stdoutMinLevel
        
    @property
    def stdoutMaxLevel(self):
        """Standard output maximum logging level."""
        return self.__stdoutMaxLevel
        
    @property
    def fileMinLevel(self):
        """file logging minimum level."""
        return self.__fileMinLevel 
        
    @property
    def fileMaxLevel(self):
        """file logging maximum level."""
        return self.__fileMaxLevel 
        
    @property
    def forcedStdoutLevels(self):
        """dictionary copy of forced flags of logging to standard output."""
        return copy.deepcopy(self.__forcedStdoutLevels)
        
    @property
    def forcedFileLevels(self):
        """dictionary copy of forced flags of logging to file."""
        return copy.deepcopy(self.__forcedFileLevels) 
        
    @property
    def logTypeNames(self):
        """dictionary copy of all defined log types logging names."""
        return copy.deepcopy(self.__logTypeNames)
        
    @property
    def logTypeLevels(self):
        """dictionary copy of all defined log types levels showing when logging."""
        return copy.deepcopy(self.__logTypeLevels)
    
    @property
    def logTypeFormats(self):
        """dictionary copy of all defined log types format showing when logging."""
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
           #. name (string): The logger name.
        """
        assert isinstance(name, basestring), "name must be a string"
        self.__name = name
    
    def set_flush(self, flush):
        """ 
        Set the logger flush flag.
    
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
           #. logType (string): A defined logging type.
           #. stdoutFlag (boolean): Whether to log to the standard output stream.
           #. fileFlag (boolean): Whether to log to to file.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag       
    
    def set_log_file(self, logfile):
        """ 
        Set the log file full path including directory path basename and extension.
    
        :Parameters:
           #. logFile (string): the full log file path including basename and 
              extension. If this is given, all of logFileBasename and logFileExtension 
              will be discarded. logfile is equivalent to logFileBasename.logFileExtension
        """
        assert isinstance(logfile, basestring), "logfile must be a string"
        basename, extension = os.path.splitext(logfile)
        self.__set_log_file_basename(logFileBasename=basename)
        self.set_log_file_extension(logFileExtension=extension)
        
    def set_log_file_extension(self, logFileExtension):
        """ 
        Set the log file extension.
    
        :Parameters:
           #. logFileExtension (string): Logging file extension. A logging file full name is 
              set as logFileBasename.logFileExtension
        """
        assert isinstance(logFileExtension, basestring), "logFileExtension must be a basestring"
        assert len(logFileExtension), "logFileExtension can't be empty"
        assert logFileExtension[0] != ".", "logFileExtension first character can't be a dot"
        assert logFileExtension[-1] != ".", "logFileExtension last character can't be a dot"
        self.__logFileExtension = logFileExtension
        # set log file name
        self.__set_log_file_name()
    
    def set_log_file_basename(self, logFileBasename):
        """ 
        Set the log file basename.
    
        :Parameters:
           #. logFileBasename (string): Logging file directory path and file basename. 
              A logging file full name is set as logFileBasename.logFileExtension
        """
        self.__set_log_file_basename(logFileBasename)
        # set log file name
        self.__set_log_file_name()
    
    def __set_log_file_basename(self, logFileBasename):
        assert isinstance(logFileBasename, basestring), "logFileBasename must be a basestring"
        self.__logFileBasename = logFileBasename
        
    def __set_log_file_name(self):
        """Automatically set logFileName attribute"""
        # ensure directory exists
        dir, _ = os.path.split(self.__logFileBasename)
        if len(dir) and not os.path.exists(dir):
            os.makedirs(dir)
        # create logFileName
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
           #. level (None, number, str): The minimum level of logging.
              If None, minimum level checking is left out.
              If str, it must be a defined logtype and therefore the minimum level would be the level of this logtype.
           #. stdoutFlag (boolean): Whether to apply this minimum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this minimum level to file logging.
        """
        # check flags
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        if not (stdoutFlag or fileFlag):
            return
        # check level
        if level is not None:
            if isinstance(level, basestring):
                level = str(level)
                assert level in self.__logTypeStdoutFlags.keys(), "level '%s' given as string, is not defined logType" %level
                level = self.__logTypeLevels[level]
            assert _is_number(level), "level must be a number"
            level = float(level)
            if stdoutFlag:
                if self.__stdoutMaxLevel is not None:
                    assert level<=self.__stdoutMaxLevel, "stdoutMinLevel must be smaller or equal to stdoutMaxLevel %s"%self.__stdoutMaxLevel
            if fileFlag:
                if self.__fileMaxLevel is not None:
                    assert level<=self.__fileMaxLevel, "fileMinLevel must be smaller or equal to fileMaxLevel %s"%self.__fileMaxLevel
        # set flags          
        if stdoutFlag:
            self.__stdoutMinLevel = level
            self.__update_stdout_flags()
        if fileFlag:
            self.__fileMinLevel = level
            self.__update_file_flags() 
               
    def set_maximum_level(self, level=0, stdoutFlag=True, fileFlag=True):
        """ 
        Set the maximum logging level. All levels above the maximum will be ignored at logging.
    
        :Parameters:
           #. level (None, number, str): The maximum level of logging.
              If None, maximum level checking is left out.
              If str, it must be a defined logtype and therefore the maximum level would be the level of this logtype.
           #. stdoutFlag (boolean): Whether to apply this maximum level to standard output logging.
           #. fileFlag (boolean): Whether to apply this maximum level to file logging.
        """
        # check flags
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        if not (stdoutFlag or fileFlag):
            return
        # check level
        if level is not None:
            if isinstance(level, basestring):
                level = str(level)
                assert level in self.__logTypeStdoutFlags.keys(), "level '%s' given as string, is not defined logType" %level
                level = self.__logTypeLevels[level]
            assert _is_number(level), "level must be a number"
            level = float(level)
            if stdoutFlag:
                if self.__stdoutMinLevel is not None:
                    assert level>=self.__stdoutMinLevel, "stdoutMaxLevel must be bigger or equal to stdoutMinLevel %s"%self.__stdoutMinLevel
            if fileFlag:
                if self.__fileMinLevel is not None:
                    assert level>=self.__fileMinLevel, "fileMaxLevel must be bigger or equal to fileMinLevel %s"%self.__fileMinLevel
        # set flags          
        if stdoutFlag:
            self.__stdoutMaxLevel = level
            self.__update_stdout_flags()
        if fileFlag:
            self.__fileMaxLevel = level  
            self.__update_file_flags()          

    def __update_flags(self):
        self.__update_stdout_flags()
        self.__update_file_flags()
        
    def __update_stdout_flags(self):
        # set stdoutMinLevel
        stdoutkeys = self.__forcedStdoutLevels.keys()
        if self.__stdoutMinLevel is not None:
            for logType, l in self.__logTypeLevels.items():
                if logType not in stdoutkeys:
                    self.__logTypeStdoutFlags[logType] = l>=self.__stdoutMinLevel
        # set stdoutMaxLevel
        if self.__stdoutMaxLevel is not None:
            for logType, l in self.__logTypeLevels.items():
                if logType not in stdoutkeys:
                    self.__logTypeStdoutFlags[logType] = l<=self.__stdoutMaxLevel
        # when stdout min and max are None
        if (self.__stdoutMinLevel is None) and (self.__stdoutMaxLevel is None):
            for logType, l in self.__logTypeLevels.items():
                if logType not in stdoutkeys:
                    self.__logTypeStdoutFlags[logType] = True
    
    def __update_file_flags(self):
        # set fileMinLevel
        filekeys = self.__forcedFileLevels.keys()
        if self.__fileMinLevel is not None:
            for logType, l in self.__logTypeLevels.items():
                if logType not in filekeys:
                    self.__logTypeFileFlags[logType] = l>=self.__fileMinLevel
        # set fileMaxLevel
        if self.__fileMaxLevel is not None:
            for logType, l in self.__logTypeLevels.items():
                if logType not in filekeys:
                    self.__logTypeFileFlags[logType] = l<=self.__fileMaxLevel
        # when file min and max are None
        if (self.__fileMinLevel is None) and (self.__fileMaxLevel is None):
            for logType, l in self.__logTypeLevels.items():
                if logType not in filekeys:
                    self.__logTypeFileFlags[logType] = True
                    
    def force_log_type_stdout_flag(self, logType, flag):
        """ 
        Force a logtype standard output logging flag despite minimum and maximum logging level boundaries.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. flag (None boolean): The standard output logging flag.
              If None, logtype existing forced flag is released.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        if flag is None:
            self.__forcedStdoutLevels.pop(logType, None)
            self.__update_stdout_flags()
        else:
            assert isinstance(flag, bool), "flag must be boolean"
            self.__logTypeStdoutFlags[logType] = flag
            self.__forcedStdoutLevels[logType] = flag
    
    def force_log_type_file_flag(self, logType, flag):
        """ 
        Force a logtype file logging flag despite minimum and maximum logging level boundaries.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. flag (None, boolean): The file logging flag.
              If None, logtype existing forced flag is released.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        if flag is None:
            self.__forcedFileLevels.pop(logType, None)
            self.__update_file_flags()
        else:
            assert isinstance(flag, bool), "flag must be boolean"
            self.__logTypeFileFlags[logType] = flag
            self.__forcedFileLevels[logType] = flag
    
    def force_log_type_flags(self, logType, stdoutFlag, fileFlag):
        """ 
        Force a logtype logging flags.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. stdoutFlag (None, boolean): The standard output logging flag.
              If None, logtype stdoutFlag forcing is released.
           #. fileFlag (None, boolean): The file logging flag.
              If None, logtype fileFlag forcing is released.
        """
        self.force_log_type_stdout_flag(logType, stdoutFlag)
        self.force_log_type_file_flag(logType, fileFlag)
        
    def set_log_type_name(self, logType, name):
        """ 
        Set a logtype name.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. name (string): The logtype new name.
        """
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' not defined" %logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        self.__logTypeNames[logType] = name
    
    def set_log_type_level(self, logType, level):
        """ 
        Set a logtype logging level.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. level (number): The level of logging.
        """
        assert _is_number(level), "level must be a number"
        level = float(level)
        name = str(name)
        self.__logTypeLevels[logType] = level
        
    def remove_log_type(self, logType, _assert=False):
        """ 
        Remove a logtype.
        
        :Parameters:
           #. logType (string): The logtype.
           #. _assert (boolean): Raise an assertion error if logType is not defined.
        """
        # check logType
        if _assert:
            assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' is not defined" %logType
        # remove logType
        self.__logTypeColor.pop(logType)
        self.__logTypeHighlight.pop(logType)
        self.__logTypeAttributes.pop(logType)
        self.__logTypeNames.pop(logType)
        self.__logTypeLevels.pop(logType)
        self.__logTypeFormat.pop(logType)
        self.__logTypeStdoutFlags.pop(logType)
        self.__logTypeFileFlags.pop(logType)
        self.__forcedStdoutLevels.pop(logType, None)
        self.__forcedFileLevels.pop(logType, None)
             
    def add_log_type(self, logType, name=None, level=0, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None):
        """ 
        Add a new logtype.
    
        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey , 
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through
        
        **N.B** *logging color, highlight and attributes are not allowed on all types of streams.*
        """
        # check logType
        assert logType not in self.__logTypeStdoutFlags.keys(), "logType '%s' already defined" %logType
        assert isinstance(logType, basestring), "logType must be a string"
        logType = str(logType)
        # set log type
        self.__set_log_type(logType=logType, name=name, level=level, 
                            stdoutFlag=stdoutFlag, fileFlag=fileFlag, 
                            color=color, highlight=highlight, attributes=attributes)
        
                
    def __set_log_type(self, logType, name, level, stdoutFlag, fileFlag, color, highlight, attributes):
        # check name
        if name is None:
            name = logType
        assert isinstance(name, basestring), "name must be a string"
        name = str(name)
        # check level
        assert _is_number(level), "level must be a number"
        level = float(level)
        # check color
        if color is not None:
            assert color in self.__stdoutFontFormat["color"], "color %s not known"%str(color)
        # check highlight
        if highlight is not None:
            assert highlight in self.__stdoutFontFormat["highlight"], "highlight %s not known"%str(highlight)
        # check attributes
        if attributes is not None:
            for attr in attributes:
                assert attr in self.__stdoutFontFormat["attributes"], "attribute %s not known"%str(attr)
        # check flags
        if stdoutFlag is not None:
            assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        if fileFlag is not None:
            assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        # set wrapFancy
        wrapFancy=["",""]
        if color is not None:
            code = self.__stdoutFontFormat["color"][color]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if highlight is not None:
            code = self.__stdoutFontFormat["highlight"][highlight]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if attributes is None:
            attributes = []
        elif isinstance(attributes, basestring):
            attributes = [str(attributes)]
        for attr in attributes:
            code = self.__stdoutFontFormat["attributes"][attr]
            if len(code):
                code = ";"+code
            wrapFancy[0] += code
        if len(wrapFancy[0]):
            wrapFancy = ["\033["+self.__stdoutFontFormat["reset"]+wrapFancy[0]+"m" , "\033["+self.__stdoutFontFormat["reset"]+"m" ]               
        # add logType
        self.__logTypeColor[logType]       = color
        self.__logTypeHighlight[logType]   = highlight
        self.__logTypeAttributes[logType]  = attributes
        self.__logTypeNames[logType]       = name
        self.__logTypeLevels[logType]      = level
        self.__logTypeFormat[logType]      = wrapFancy
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        if stdoutFlag is not None:
            self.__forcedStdoutLevels[logType] = stdoutFlag
        else:
            self.__forcedStdoutLevels.pop(logType, None)
            self.__update_stdout_flags()
        self.__logTypeFileFlags[logType] = fileFlag
        if fileFlag is not None:
            self.__forcedFileLevels[logType] = fileFlag
        else:
            self.__forcedFileLevels.pop(logType, None)
            self.__update_file_flags()

    def update_log_type(self, logType, name=None, level=None, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None):
        """ 
        update a logtype.
    
        :Parameters:
           #. logType (string): The logtype.
           #. name (None, string): The logtype name. If None, name will be set to logtype.
           #. level (number): The level of logging.
           #. stdoutFlag (None, boolean): Force standard output logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. fileFlag (None, boolean): Force file logging flag.
              If None, flag will be set according to minimum and maximum levels.
           #. color (None, string): The logging text color. The defined colors are:\n
              black , red , green , orange , blue , magenta , cyan , grey , dark grey , 
              light red , light green , yellow , light blue , pink , light cyan
           #. highlight (None, string): The logging text highlight color. The defined highlights are:\n
              black , red , green , orange , blue , magenta , cyan , grey
           #. attributes (None, string): The logging text attribute. The defined attributes are:\n
              bold , underline , blink , invisible , strike through
        
        **N.B** *logging color, highlight and attributes are not allowed on all types of streams.*
        """
        # check logType
        assert logType in self.__logTypeStdoutFlags.keys(), "logType '%s' is not defined" %logType
        # get None updates
        if name is None:       name       = self.__logTypeNames[logType]
        if level is None:      level      = self.__logTypeLevels[logType]
        if stdoutFlag is None: stdoutFlag = self.__logTypeStdoutFlags[logType]
        if fileFlag is None:   fileFlag   = self.__logTypeFileFlags[logType]
        if color is None:      color      = self.__logTypeColor[logType]
        if highlight is None:  highlight  = self.__logTypeHighlight[logType]
        if attributes is None: attributes = self.__logTypeAttributes[logType]
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
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
        """
        # log to stdout
        if self.__logToStdout and self.__logTypeStdoutFlags[logType]:
            log = self._format_message(logType, message)
            log = self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n"
            self.__log_to_stdout(log)
            if self.__flush:
                try:
                    self.__stdout.flush()
                except:
                    pass
                try:
                    os.fsync(self.__stdout.fileno())
                except:
                    pass
        # log to file
        if self.__logToFile and self.__logTypeFileFlags[logType]:
            log = self._format_message(logType, message)
            self.__log_to_file(log+"\n")
            if self.__flush:
                try:
                    self.__logFileStream.flush()
                except:
                    pass
                try:
                    os.fsync(self.__logFileStream.fileno())
                except:
                    pass
        # set last logged message
        self.__lastLogged[logType] = message
        self.__lastLogged[-1]      = message
    
    def force_log(self, logType, message, stdout=True, file=True):
        """ 
        Force logging a message of a certain logtype whether logtype level is allowed or not.
    
        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. stdout (boolean): Whether to force logging to standard output.
           #. file (boolean): Whether to force logging to file.
        """
        # log to stdout
        if stdout:
            log = self._format_message(logType, message)
            log = self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n"
            self.__log_to_stdout(log)
            try:
                self.__stdout.flush()
            except:
                pass
            try:
                os.fsync(self.__stdout.fileno())
            except:
                pass
        if file:    
            # log to file
            log = self._format_message(logType, message)
            self.__log_to_file(log+"\n")
            try:
                self.__logFileStream.flush()
            except:
                pass
            try:
                os.fsync(self.__logFileStream.fileno())
            except:
                pass
        # set last logged message
        self.__lastLogged[logType] = message
        self.__lastLogged[-1]      = message
            
    def flush(self):
        """Flush all streams."""
        if self.__logFileStream is not None:
            try:
                self.__logFileStream.flush()
            except:
                pass
            try:
                os.fsync(self.__logFileStream.fileno())
            except:
                pass
        if self.__stdout is not None:
            try:
                self.__stdout.flush()
            except:
                pass
            try:
                os.fsync(self.__stdout.fileno())
            except:
                pass
        
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
    print(l, '\n')
    # print available logs and logging time.
    for logType in l.logTypes:
        tic = time.clock()
        l.log(logType, "this is '%s' level log message."%logType)
        print("%s seconds\n"%str(time.clock()-tic))
        
        
        

    
