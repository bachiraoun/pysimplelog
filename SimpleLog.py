"""
Usage
=====
    .. code-block:: python

        # import python 2.7.x 3.x.y compatible print function
        from __future__ import print_function
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
        print(l, end="\\n\\n")

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
        print("")
        print("Last logged messages are:")
        print("=========================")
        print(l.lastLoggedMessage)
        print(l.lastLoggedDebug)
        print(l.lastLoggedInfo)
        print(l.lastLoggedWarning)
        print(l.lastLoggedError)
        print(l.lastLoggedCritical)

        # log data
        print("")
        print("Log random data and traceback stack:")
        print("====================================")
        l.info("Check out this data", data=list(range(10)))
        print("")

        # log error with traceback
        import traceback
        try:
            1/range(10)
        except Exception as err:
            l.error('%s (is this python ?)'%err, tback=traceback.extract_stack())


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

            2018-09-07 16:07:58 - log test &#60INFO&#62 I am info, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60INFO&#62 I am  info, called using log method.
            2018-09-07 16:07:58 - log test &#60WARNING&#62 I am warn, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60WARNING&#62 I am warn, called using log method.
            <font color="pink"><b><ins>2018-09-07 16:07:58 - log test &#60ERROR&#62 I am error, called using my shortcut method.</ins></b></font>
            <font color="pink"><b><ins>2018-09-07 16:07:58 - log test &#60ERROR&#62 I am error, called using log method.</ins></b></font>
            2018-09-07 16:07:58 - log test &#60CRITICAL&#62 I am critical, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60CRITICAL&#62 I critical, called using log method.
            2018-09-07 16:07:58 - log test &#60DEBUG&#62 I am debug, called using my shortcut method.
            2018-09-07 16:07:58 - log test &#60DEBUG&#62 I am debug, called using log method.
            <font color="red"><b><ins>2018-09-07 16:07:58 - log test &#60SUPER CRITICAL&#62 I am super critical, called using log method because I have no shortcut method.</ins></b></font>
            <font color="magenta"><del>2018-09-07 16:07:58 - log test &#60info&#62 I am wrong, called using log method because I have no shortcut method.</del></font>
            <style>mark{background-color: orange}</style><mark><b>2015-11-18 14:25:08 - log test &#60info&#62 I am important, called using log method because I have no shortcut method.</b></mark>

            Last logged messages are:
            =========================
            I am important, called using log method because I have no shortcut method.
            I am debug, called using log method.
            I am  info, called using log method.
            I am warn, called using log method.
            I am error, called using log method.
            I am critical, called using log method.

            Log random data and traceback stack:
            ====================================
            2018-09-07 16:07:58 - log test <INFO> Check out this data
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            <font color="pink"><b><ins>2015-11-18 14:25:08 - log test &#60ERROR&#62 unsupported operand type(s) for /: 'int' and 'list' (is this python ?)</ins></b></font>
            <font color="pink"><b><ins>  File "&#60stdin&#62", line 4, in &#60module&#62</ins></b></font>


        </pre>
        <body>

"""
# python standard distribution imports
import os, sys, copy, re, atexit
from datetime import datetime

# python version dependant imports
if sys.version_info >= (3, 0):
    # This is python 3
    str        = str
    long       = int
    unicode    = str
    bytes      = bytes
    basestring = str
else:
    str        = str
    unicode    = unicode
    bytes      = str
    long       = long
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

def _normalize_path(path):
    if os.sep=='\\':
        path = re.sub(r'([\\])\1+', r'\1', path).replace('\\','\\\\')
    return path


class Logger(object):
    """
    This is simplelog main Logger class definition.\n

    A logging is constituted of a header a message and a footer.
    In the current implementation the footer is empty and the header is as the following:\n
    date time - loggerName <logTypeName>\n

    In order to change any of the header or the footer, '_get_header' and '_get_footer'
    methods must be overloaded.

    When used in a python application, it is advisable to use Logger singleton
    implementation and not Logger itself.
    if no overloading is needed one can simply import the singleton as the following:

    .. code-block:: python

        from pysimplelog import SingleLogger as Logger


    A new Logger instanciates with the following logType list (logTypes <NAME>: level)

       * debug <DEBUG>: 0
       * info <INFO>: 10
       * warn <WARNING>: 20
       * error <ERROR>: 30
       * critical <CRITICAL>: 100


    Recommended overloading implementation, this is how it could be done:

    .. code-block:: python

        from pysimplelog import SingleLogger as LOG

        class Logger(LOG):
            # *args and **kwargs can be replace by fixed arguments
            def custom_init(self, *args, **kwargs):
                # hereinafter any further instanciation can be coded



    In case overloading __init__ is needed, this is how it could be done:

    .. code-block:: python

        from pysimplelog import SingleLogger as LOG

        class Logger(LOG):
            # custom_init will still be called in super(Logger, self).__init__(*args, **kwargs)
            def __init__(self, *args, **kwargs):
                if self._isInitialized: return
                super(Logger, self).__init__(*args, **kwargs)
                # hereinafter any further instanciation can be coded


    :Parameters:
       #. name (string): The logger name.
       #. flush (boolean): Whether to always flush the logging streams.
       #. logToStdout (boolean): Whether to log to the standard output stream.
       #. stdout (None, stream): The standard output stream. If None, system
          standard output will be set automatically. Otherwise any stream with
          read and write methods can be passed
       #. logToFile (boolean): Whether to log to to file.
       #. logFile (None, string): the full log file path including directory
          basename and extension. If this is given, all of logFileBasename and
          logFileExtension will be discarded. logfile is equivalent to
          logFileBasename.logFileExtension
       #. logFileBasename (string): Logging file directory path and file
          basename. A logging file full name is set as
          logFileBasename.logFileExtension
       #. logFileExtension (string): Logging file extension. A logging file
          full name is set as logFileBasename.logFileExtension
       #. logFileMaxSize (None, number): The maximum size in Megabytes
          of a logging file. Once exceeded, another logging file as
          logFileBasename_N.logFileExtension will be created.
          Where N is an automatically incremented number. If None or a
          negative number is given, the logging file will grow
          indefinitely
       #. logFileFirstNumber (None, integer): first log file number 'N' in
          logFileBasename_N.logFileExtension. If None is given then
          first log file will be logFileBasename.logFileExtension and ince
          logFileMaxSize is reached second log file will be
          logFileBasename_0.logFileExtension and so on and so forth.
          If number is given it must be an integer >=0
       #. logFileRoll (None, intger): If given, it sets the maximum number of
          log files to write. Exceeding the number will result in deleting
          previous ones. This also insures always increasing files numbering.
       #. stdoutMinLevel(None, number): The minimum logging to system standard
          output level. If None, standard output minimum level checking is left
          out.
       #. stdoutMaxLevel(None, number): The maximum logging to system standard
          output level. If None, standard output maximum level checking is
          left out.
       #. fileMinLevel(None, number): The minimum logging to file level.
          If None, file minimum level checking is left out.
       #. fileMaxLevel(None, number): The maximum logging to file level.
          If None, file maximum level checking is left out.
       #. logTypes (None, dict): Used to create and update existing log types
          upon initialization. Given dictionary keys are logType
          (new or existing) and values can be None or a dictionary of kwargs
          to call update_log_type upon. This argument will be called after
          custom_init
       #. timezone (None, str): Logging time timezone. If provided
          pytz must be installed and it must be the timezone name. If not
          provided, the machine default timezone will be used.
       #. \*args: This is used to send non-keyworded variable length argument
           list to custom initialize. args will be parsed and used in
           custom_init method.
       #. \**kwargs: This allows passing keyworded variable length of
           arguments to custom_init method. kwargs can be anything other
           than __init__ arguments.
    """
    def __init__(self, name="logger", flush=True,
                       logToStdout=True, stdout=None,
                       logToFile=True, logFile=None,
                       logFileBasename="simplelog", logFileExtension="log",
                       logFileMaxSize=10, logFileFirstNumber=0, logFileRoll=None,
                       stdoutMinLevel=None, stdoutMaxLevel=None,
                       fileMinLevel=None, fileMaxLevel=None,
                       logTypes=None, timezone=None,*args, **kwargs):
        # set last logged message
        self.__lastLogged    = {}
        # instanciate file stream
        self.__logFileStream = None
        # set timezone
        self.set_timezone(timezone)
        # set name
        self.set_name(name)
        # set flush
        self.set_flush(flush)
        # set log to stdout
        self.set_log_to_stdout_flag(logToStdout)
        # set stdout
        self.set_stdout(stdout)
        # set log file roll
        self.set_log_file_roll(logFileRoll)
        # set log to file
        self.set_log_to_file_flag(logToFile)
        # set maximum logFile size
        self.set_log_file_maximum_size(logFileMaxSize)
        # set logFile first number
        self.set_log_file_first_number(logFileFirstNumber)
        # set logFile basename and extension
        if logFile is not None:
            self.set_log_file(logFile)
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
        self.add_log_type("debug",    name="DEBUG",    level=0,   stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("info",     name="INFO",     level=10,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("warn",     name="WARNING",  level=20,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("error",    name="ERROR",    level=30,  stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        self.add_log_type("critical", name="CRITICAL", level=100, stdoutFlag=None, fileFlag=None, color=None, highlight=None, attributes=None)
        # custom initialize
        self.custom_init( *args, **kwargs )
        # add logTypes
        if logTypes is not None:
            assert isinstance(logTypes, dict),"logTypes must be None or a dictionary"
            assert all([isinstance(lt, basestring) for lt in logTypes]), "logTypes dictionary keys must be strings"
            assert all([isinstance(logTypes[lt], dict) for lt in logTypes if logTypes[lt] is not None]), "logTypes dictionary values must be all None or dictionaries"
            for lt in logTypes:
                ltv = logTypes[lt]
                if ltv is None:
                    ltv = {}
                if not self.is_logType(lt):
                    self.add_log_type(lt, **ltv)
                elif len(ltv):
                    self.update_log_type(lt, **ltv)
        # flush at python exit
        atexit.register(self._flush_atexit_logfile)

    def __str__(self):
        # create version
        string  = self.__class__.__name__+" (Version "+str(__version__)+")"
        # add general properties
        #string += "\n - Log To Standard Output General Flag:  %s"%(self.__logToStdout)
        #string += "\n - Log To Standard Output Minimum Level: %s"%(self.__stdoutMinLevel)
        #string += "\n - Log To Standard Output Maximum Level: %s"%(self.__stdoutMaxLevel)
        #string += "\n - Log To File General Flag:  %s"%(self.__logToFile)
        #string += "\n - Log To File Minimum Level: %s"%(self.__fileMinLevel)
        #string += "\n - Log To File Maximum Level: %s"%(self.__fileMaxLevel)
        string += "\n - Log To Stdout: Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToStdout,self.__stdoutMinLevel,self.__stdoutMaxLevel)
        string += "\n - Log To File:   Flag (%s) - Min Level (%s) - Max Level (%s)"%(self.__logToFile,self.__fileMinLevel,self.__fileMaxLevel)
        string += "\n                  File Size (%s) - First Number (%s) - Roll (%s)"%(self.__logFileMaxSize,self.__logFileFirstNumber,self.__logFileRoll)
        string += "\n                  Current log file (%s)"%(self.__logFileName)
        # add log types table
        if not len(self.__logTypeNames):
            string += "\nlog type  |log name  |level     |std flag   |file flag"
            string += "\n----------|----------|----------|-----------|---------"
            return string
        # get maximum logType and logTypeZName and maxLogLevel
        maxLogType  = max( max([len(k)+1 for k in self.__logTypeNames]),   len("log type  "))
        maxLogName  = max( max([len(self.__logTypeNames[k])+1 for k in self.__logTypeNames]), len("log name  "))
        maxLogLevel = max( max([len(str(self.__logTypeLevels[k]))+1 for k in self.__logTypeLevels]), len("level     "))
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
        keys = sorted(self.__logTypeLevels, key=self.__logTypeLevels.__getitem__)
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
        return list(self.__logTypeNames)

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
    def logFileRoll(self):
        """Log file roll parameter."""
        return self.__logFileRoll

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
        return self.__logFileMaxSize

    @property
    def logFileFirstNumber(self):
        """log file first number"""
        return self.__logFileFirstNumber

    @property
    def timezone(self):
        """The timezone if given"""
        timezone = self.__timezone
        if timezone is not None:
            timezone = timezone.zone
        return timezone

    def set_timezone(self, timezone):
        """
        Set logging timezone

        :Parameters:
            #. timezone (None, str): Logging time timezone. If provided
               pytz must be installed and it must be the timezone name. If not
               provided, the machine default timezone will be used
        """
        if timezone is not None:
            assert isinstance(timezone, basestring), "timezone must be None or a string"
            import pytz
            timezone = pytz.timezone(timezone)
        self.__timezone = timezone

    def is_logType(self, logType):
        """
        Get whether given logType is defined or not

        :Parameters:
           #. logType (string): A defined logging type.

        :Result:
           #. result (boolean): Whether given logType is defined or not
        """
        try:
            result = logType in self.__logTypeNames
        except:
            result = False
        finally:
            return result

    def update(self, **kwargs):
        """Update logger general parameters using key value pairs.
        Updatable parameters are name, flush, stdout, logToStdout, logFileRoll,
        logToFile, logFileMaxSize, stdoutMinLevel, stdoutMaxLevel, fileMinLevel,
        fileMaxLevel and logFileFirstNumber.
        """
        # update name
        if "name" in kwargs:
            self.set_name(kwargs["name"])
        # update flush
        if "flush" in kwargs:
            self.set_flush(kwargs["flush"])
        # update stdout
        if "stdout" in kwargs:
            self.set_stdout(kwargs["stdout"])
        # update logToStdout
        if "logToStdout" in kwargs:
            self.set_log_to_stdout_flag(kwargs["logToStdout"])
        # update logFileRoll
        if "logFileRoll" in kwargs:
            self.set_log_file_roll(kwargs["logFileRoll"])
        # update logToFile
        if "logToFile" in kwargs:
            self.set_log_to_file_flag(kwargs["logToFile"])
        # update logFileMaxSize
        if "logFileMaxSize" in kwargs:
            self.set_log_file_maximum_size(kwargs["logFileMaxSize"])
        # update logFileFirstNumber
        if "logFileFirstNumber" in kwargs:
            self.set_log_file_first_number(kwargs["logFileFirstNumber"])
        # update stdoutMinLevel
        if "stdoutMinLevel" in kwargs:
            self.set_minimum_level(kwargs["stdoutMinLevel"], stdoutFlag=True, fileFlag=False)
        # update stdoutMaxLevel
        if "stdoutMaxLevel" in kwargs:
            self.set_maximum_level(kwargs["stdoutMaxLevel"], stdoutFlag=True, fileFlag=False)
        # update fileMinLevel
        if "fileMinLevel" in kwargs:
            self.set_minimum_level(kwargs["fileMinLevel"], stdoutFlag=False, fileFlag=True)
        # update fileMaxLevel
        if "fileMaxLevel" in kwargs:
            self.set_maximum_level(kwargs["fileMaxLevel"], stdoutFlag=False, fileFlag=True)
        # update logfile
        if "logFile" in kwargs:
            self.set_log_file(kwargs["logFile"])


    @property
    def parameters(self):
        """get a dictionary of logger general parameters. The same dictionary
        can be used to update another logger instance using update method"""
        return {"name":self.__name,
                "flush":self.__flush,
                "stdout":None if self.__stdout is sys.stdout else self.__stdout,
                "logToStdout":self.__logToStdout,
                "logFileRoll":self.__logFileRoll,
                "logToFile":self.__logToFile,
                "logFileMaxSize":self.__logFileMaxSize,
                "logFileFirstNumber":self.__logFileFirstNumber,
                "stdoutMinLevel":self.__stdoutMinLevel,
                "stdoutMaxLevel":self.__stdoutMaxLevel,
                "fileMinLevel":self.__fileMinLevel,
                "fileMaxLevel":self.__fileMaxLevel,
                "logFile":self.__logFileBasename+"."+self.__logFileExtension}


    def custom_init(self, *args, **kwargs):
        """
        Custom initialize abstract method. This method will be called  at the end of
        initialzation. This method needs to be overloaded to custom initialize
        Logger instances.

        :Parameters:
            #. \*args (): This is used to send non-keyworded variable length argument
               list to custom initialize.
            #. \**kwargs (): This is keyworded variable length of arguments.
               kwargs can be anything other than __init__ arguments.
        """
        pass

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
        Set the logging to the defined standard output flag. When set to False,
        no logging to  standard output will happen regardless of a logType
        standard output flag.

        :Parameters:
           #. logToStdout (boolean): Whether to log to the standard output stream.
        """
        assert isinstance(logToStdout, bool), "logToStdout must be boolean"
        self.__logToStdout = logToStdout

    def set_log_to_file_flag(self, logToFile):
        """
        Set the logging to a file general flag. When set to False, no logging
        to file will happen regardless of a logType file flag.

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
        assert logType in self.__logTypeStdoutFlags, "logType '%s' not defined" %logType
        assert isinstance(stdoutFlag, bool), "stdoutFlag must be boolean"
        assert isinstance(fileFlag, bool), "fileFlag must be boolean"
        self.__logTypeStdoutFlags[logType] = stdoutFlag
        self.__logTypeFileFlags[logType]   = fileFlag

    def set_log_file_roll(self, logFileRoll):
        """
        Set roll parameter to determine the maximum number of log files allowed.
        Beyond the maximum, older will be removed.

        :Parameters:
            #. logFileRoll (None, intger): If given, it sets the maximum number of
               log files to write. Exceeding the number will result in deleting
               older files. This also insures always increasing files numbering.
               Log files will be identified in increasing N order of
               logFileBasename_N.logFileExtension pattern. Be careful setting
               this parameter as old log files will be permanently deleted if
               the number of files exceeds the value of logFileRoll
        """
        if logFileRoll is not None:
            assert isinstance(logFileRoll, int), "logFileRoll must be None or integer"
            assert logFileRoll>0, "integer logFileRoll must be >0"
        self.__logFileRoll = logFileRoll

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
        if logFileExtension[0] == ".":
            logFileExtension = logFileExtension[1:]
        assert len(logFileExtension), "logFileExtension is not allowed to be single dot"
        if logFileExtension[-1] == ".":
            logFileExtension = logFileExtension[:-1]
        assert len(logFileExtension), "logFileExtension is not allowed to be double dots"
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
        self.__logFileBasename = _normalize_path(logFileBasename)#logFileBasename

    def __set_log_file_name(self):
        """Automatically set logFileName attribute"""
        # ensure directory exists
        dir, _ = os.path.split(self.__logFileBasename)
        if len(dir) and not os.path.exists(dir):
            os.makedirs(dir)
        # get existing logfiles
        numsLUT  = {}
        filesLUT = {}
        ordered  = []
        if not len(dir) or os.path.isdir(dir):
            listDir = os.listdir(dir) if len(dir) else os.listdir('.')
            for f in listDir:
                p = os.path.join(dir,f)
                if not os.path.isfile(p):
                    continue
                if re.match("^{bsn}(_\\d+)?.{ext}$".format(bsn=self.__logFileBasename, ext=self.__logFileExtension), p) is None:
                    continue
                n = p.split(self.__logFileBasename)[1].split('.%s'%self.__logFileExtension)[0]
                n = int(n[1:]) if len(n) else ''
                assert n not in numsLUT , "filelog number is found in LUT shouldn't have happened. PLEASE REPORT BUG"
                numsLUT[n]  = p
                filesLUT[p] = n
            ordered = ([''] if '' in numsLUT else []) + sorted([n for n in numsLUT if isinstance(n, int)])
            ordered = [numsLUT[n] for n in ordered]
        # get last file number
        if len(ordered):
            number = filesLUT[ordered[-1]]
        else:
            number = self.__logFileFirstNumber
        # limit number of log files to logFileRoll
        if self.__logFileRoll is not None:
            while len(ordered)>self.__logFileRoll:
                os.remove(ordered.pop(0))
            if len(ordered) == self.__logFileRoll and self.__logFileMaxSize is not None:
                if os.stat(ordered[-1]).st_size/(1024.**2) >= self.__logFileMaxSize:
                #if os.stat(ordered[-1]).st_size/1e6 >= self.__logFileMaxSize:
                    os.remove(ordered.pop(0))
                    if isinstance(number, int):
                        number = number + 1
        # temporarily set self.__logFileName
        if not isinstance(number, int):
            self.__logFileName = self.__logFileBasename+"."+self.__logFileExtension
            number = -1
        else:
            self.__logFileName = self.__logFileBasename+"_"+str(number)+"."+self.__logFileExtension
        # check temporarily set logFileName file size
        if self.__logFileMaxSize is not None:
            while os.path.isfile(self.__logFileName):
                if os.stat(self.__logFileName).st_size/(1024.**2) < self.__logFileMaxSize:
                #if os.stat(self.__logFileName).st_size/1e6 < self.__logFileMaxSize:
                    break
                number += 1
                self.__logFileName = self.__logFileBasename+"_"+str(number)+"."+self.__logFileExtension
        # create log file stream
        if self.__logFileStream is not None:
            try:
                self.__logFileStream.close()
            except:
                pass
        self.__logFileStream = None

    def set_log_file_maximum_size(self, logFileMaxSize):
        """
        Set the log file maximum size in megabytes

        :Parameters:
           #. logFileMaxSize (None, number): The maximum size in Megabytes
              of a logging file. Once exceeded, another logging file as
              logFileBasename_N.logFileExtension will be created.
              Where N is an automatically incremented number. If None or a
              negative number is given, the logging file will grow
              indefinitely
        """
        if logFileMaxSize is not None:
            assert _is_number(logFileMaxSize), "logFileMaxSize must be a number"
            logFileMaxSize = float(logFileMaxSize)
            if logFileMaxSize <=0:
                logFileMaxSize = None
        #assert logFileMaxSize>=1, "logFileMaxSize minimum size is 1 megabytes"
        self.__logFileMaxSize = logFileMaxSize

    def set_log_file_first_number(self, logFileFirstNumber):
        """
        Set log file first number

        :Parameters:
            #. logFileFirstNumber (None, integer): first log file number 'N' in
               logFileBasename_N.logFileExtension. If None is given then
               first log file will be logFileBasename.logFileExtension and ince
               logFileMaxSize is reached second log file will be
               logFileBasename_0.logFileExtension and so on and so forth.
               If number is given it must be an integer >=0
        """
        if logFileFirstNumber is not None:
            assert isinstance(logFileFirstNumber, int), "logFileFirstNumber must be None or an integer"
            assert logFileFirstNumber>=0, "logFileFirstNumber integer must be >=0"
        self.__logFileFirstNumber = logFileFirstNumber

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
                assert level in self.__logTypeStdoutFlags, "level '%s' given as string, is not defined logType" %level
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
                assert level in self.__logTypeStdoutFlags, "level '%s' given as string, is not defined logType"%level
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
        stdoutkeys = list(self.__forcedStdoutLevels)
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
        filekeys = list(self.__forcedFileLevels)
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
        assert logType in self.__logTypeStdoutFlags, "logType '%s' not defined" %logType
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
        assert logType in self.__logTypeStdoutFlags, "logType '%s' not defined" %logType
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
        assert logType in self.__logTypeStdoutFlags, "logType '%s' not defined" %logType
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
            assert logType in self.__logTypeStdoutFlags, "logType '%s' is not defined" %logType
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
        assert logType not in self.__logTypeStdoutFlags, "logType '%s' already defined" %logType
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
        assert logType in self.__logTypeStdoutFlags, "logType '%s' is not defined" %logType
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

    def _format_message(self, logType, message, data, tback):
        header = self._get_header(logType, message)
        footer = self._get_footer(logType, message)
        dataStr  = ''
        tbackStr = ''
        if data is not None:
            #dataStr = '\n%s'%(repr(data))
            dataStr = '\n%s'%(data,)
        if tback is not None:
            if isinstance(tback, str):
                tbackStr = '\n%s'%(tback,)
            else:
                try:
                    tbackStr = []
                    for filename, lineno, name, line in tback:
                        tbackStr.append( '\n  File "%s", line %d, in %s'%(filename,lineno,name) )
                        if line:
                            tbackStr.append( '\n    %s'%(line.strip(),) )
                    tbackStr = ''.join(tbackStr)
                except:
                    tbackStr = '\n%s'%(str(tback),)
        return "%s%s%s%s%s" %(header, message, footer, dataStr, tbackStr)

    def _get_header(self, logType, message):
        dateTime = datetime.strftime(datetime.now(self.__timezone), '%Y-%m-%d %H:%M:%S')
        return "%s - %s <%s> "%(dateTime, self.__name, self.__logTypeNames[logType])

    def _get_footer(self, logType, message):
        return ""

    def __log_to_file(self, message):
        # create log file stream
        if self.__logFileStream is None:
            self.__logFileStream = open(self.__logFileName, 'a')
        elif self.__logFileMaxSize is not None:
            if self.__logFileStream.tell()/(1024.**2) >= self.__logFileMaxSize:
            #if self.__logFileStream.tell()/1e6 >= self.__logFileMaxSize:
                self.__set_log_file_name()
                self.__logFileStream = open(self.__logFileName, 'a')
        # log to file
        # no need to try and catch. even when main thread dies a file handler
        # shouldn't close
        self.__logFileStream.write(message)

    def __log_to_stdout(self, message):
        try:
            self.__stdout.write(message)
        except:
            # for the rare case when stdout buffer no more exits.
            # this can happen when main thread dies and all remaining threads
            # turn to daemon threads. Try and catch add absolutely no
            # overhead unless when an error occurs.
            pass

    def is_enabled_for_stdout(self, logType):
        """Get whether given logtype is enabled for standard output logging.
        When a logType is not enabled, calling for log will return without
        logging.
        This method will check general standard output logging flag and given
        logType standard output flag. For a logType to log it must have both
        flags set to True

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): whehter enabled or not.
        """
        return self.__logToStdout and self.__logTypeStdoutFlags[logType]

    def is_enabled_for_file(self, logType):
        """Get whether given logtype is enabled for file logging.
        When a logType is not enabled, calling for log will return without
        logging.
        This method will check general file logging flag and given
        logType file flag. For a logType to log it must have both
        flags set to True

        :Parameters:
           #. logType (string): A defined logging type.

        :Returns:
           #. enabled (bool): whehter enabled or not.
        """
        return self.__logToFile and self.__logTypeFileFlags[logType]


    def log(self, logType, message, data=None, tback=None):
        """
        log a message of a certain logtype.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. data (None,  object): Any type of data to print and/or write to log file
              after log message
           #. tback (None, str, list): Stack traceback to print and/or write to
              log file. In general, this should be traceback.extract_stack

        :Returns:
            #. message (string): the logged message
        """
        # log to stdout
        log = self._format_message(logType=logType, message=message, data=data, tback=tback)
        if self.__logToStdout and self.__logTypeStdoutFlags[logType]:
            #self.__log_to_stdout(self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n")
            self.__log_to_stdout("%s%s%s\n"%(self.__logTypeFormat[logType][0],log,self.__logTypeFormat[logType][1]))
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
            self.__log_to_file("%s\n"%log)
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
        self.__lastLogged[logType] = log
        self.__lastLogged[-1]      = log
        # always return logged message
        return message

    def force_log(self, logType, message, data=None, tback=None, stdout=True, file=True):
        """
        Force logging a message of a certain logtype whether logtype level is allowed or not.

        :Parameters:
           #. logType (string): A defined logging type.
           #. message (string): Any message to log.
           #. tback (None, str, list): Stack traceback to print and/or write to
              log file. In general, this should be traceback.extract_stack
           #. stdout (boolean): Whether to force logging to standard output.
           #. file (boolean): Whether to force logging to file.

        :Returns:
            #. message (string): the logged message
        """
        # log to stdout
        log = self._format_message(logType=logType, message=message, data=data, tback=tback)
        if stdout:
            #self.__log_to_stdout(self.__logTypeFormat[logType][0] + log + self.__logTypeFormat[logType][1] + "\n")
            self.__log_to_stdout("%s%s%s\n"%(self.__logTypeFormat[logType][0],log,self.__logTypeFormat[logType][1]))
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
            self.__log_to_file("%s\n"%log)
            try:
                self.__logFileStream.flush()
            except:
                pass
            try:
                os.fsync(self.__logFileStream.fileno())
            except:
                pass
        # set last logged message
        self.__lastLogged[logType] = log
        self.__lastLogged[-1]      = log
        # always return logged message
        return message

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

    def info(self, message, *args, **kwargs):
        """alias to message at information level"""
        return self.log("info", message, *args, **kwargs)

    def information(self, message, *args, **kwargs):
        """alias to message at information level"""
        return self.log("info", message, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        """alias to message at warning level"""
        return self.log("warn", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """alias to message at warning level"""
        return self.log("warn", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """alias to message at error level"""
        return self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """alias to message at critical level"""
        return self.log("critical", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """alias to message at debug level"""
        return self.log("debug", message, *args, **kwargs)



class SingleLogger(Logger):
    """
    This is singleton implementation of Logger class.
    """
    __thisInstance = None
    def __new__(cls, *args, **kwds):
        if cls.__thisInstance is None:
            cls.__thisInstance = super(SingleLogger,cls).__new__(cls)
            cls.__thisInstance._isInitialized = False
        return cls.__thisInstance

    def __init__(self, *args, **kwargs):
        if (self._isInitialized): return
        # initialize
        super(SingleLogger, self).__init__(*args, **kwargs)
        # update flag
        self._isInitialized = True



if __name__ == "__main__":
    import time
    l=Logger("log test")
    l.add_log_type("super critical", name="SUPER CRITICAL", level=200, color='red', attributes=["bold","underline"])
    l.add_log_type("wrong", name="info", color='magenta', attributes=["strike through"])
    l.add_log_type("important", name="info", color='black', highlight="orange", attributes=["bold","blink"])
    print(l, '\n')
    # print available logs and logging time.
    for logType in l.logTypes:
        tic = time.time()
        l.log(logType, "this is '%s' level log message."%logType)
        print("%s seconds\n"%str(time.time()-tic))
