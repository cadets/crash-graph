#!/usr/local/bin/python

"""
"""

import lldb
import os
import sys
import signal
from enum import Enum

class CGRegister:
    def __init__(self, name="", num_children=0, value=0):
        self.name = name
        self.num_children = num_children
        self.value = value

    def GetName():
        return self.name

    def GetNumChildren():
        return self.num_children

    def GetValue():
        return self.value

class CGFrameEntryType(Enum):
    FUNCTION = 1
    SYMBOL   = 2

class CGFrameEntry:
    def __init__(self, ftype="", name="", fetype=CGFrameEntryType.FUNCTION):
        self.name = name
        self.type = fetype # Frame entry type
        self.ftype = ftype # Function type

    def SetName(self, name):
        self.name = name

    def GetName(self):
        return self.name

    def SetType(self, fetype):
        self.type = fetype

    def GetType(self):
        return self.type

class CGFunction(CGFrameEntry):
    """
    Currently, we only use CGFunction as a type of CGFrameEntry, CGSymbol is
    unused.

    We keep a dictionary of arguments in the function so that we can access
    their values with their name in the scope of one frame.
    """
    def __init__(self, ftype="", name="", args={}):
        CGFrameEntry.__init__(self, ftype, name)
        self.args = args

    def SetArgs(self, args):
        self.args = args

    def AddArg(self, argtype, argname, argval):
        self.args[argname] = (argtype, argval)

    def GetArg(self, argname):
        return self.args[argname]

    def GetArgValue(self, argname):
        return self.args[argname][0]

    def GetArgType(self, argname):
        return self.args[argname][1]

    def NumberOfArgs(self):
        return len(self.args)

    def SetArg(self, argtype, argname, argval):
        if self.args[argname]:
            self.args[argname] = (argtype, argval)

    def GetArgs(self):
        return self.args

    def GetType(self):
        return self.ftype

class CGSymbol(CGFrameEntry):
    """
    This is currently unused, but we might wish to abstract it away using this
    method later on.
    """
    def __init__(self, name=""):
        CGFrameEntry.__init__(self, name, CGFrameEntryType.SYMBOL)

class CGFrame:
    def __init__(self, cgfun=None, cgregs=None):
        self.cgfun = cgfun
        self.cgregs = cgregs

    def SetRegisters(self, cgregs):
        self.cgregs = cgregs

    def GetRegisters(self):
        return self.cgregs

    def SetFunction(self, cgfun):
        self.cgfun = cgfun

    def GetFunction(self):
        return self.cgfun

class CGCrash:
    """
    We use CGCrash to keep the information of a full crash. It contains the
    backtrace stack, which we pop off entry by entry until it's empty.

    We also record the registers for each frame inside of this class with the
    purpose of more detailed analysis later on.
    """
    def __init__(self, frames=[], thread=None, name="GenericCrashName"):
        self.frames = frames
        self.thread = thread

    def AddFrame(self, cgframe):
        self.frames.append(cgframe)

    def SetThread(self, thread):
        self.thread = thread

    def GetThread(self):
        return self.thread

    def GetBacktrace(self):
        return self.frames



class CGDebugger:
    def __init__(self, binary_path='./a.out', indata='out',
            sigstocatch=[signal.SIGSEGV, signal.SIGABRT]):
        # We hook into lldb here
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        # Create the debugging target and identify which signals we want to
        # catch
        self.target = self.debugger.CreateTarget(binary_path)
        self.sigstocatch = sigstocatch

        self.crashes = []

    def Run(self):
        if self.target:
            # Launch the process
            process = self.target.LaunchSimple(None, None, os.getcwd())
            cgcrash = CGCrash()
            if process:
                print process
                state = process.GetState()
                if state == lldb.eStateStopped:
                    thread = process.GetThreadAtIndex(0)
                    
                    if thread:
                        cgcrash.SetThread(thread)
                        print thread

                        # We only want to examine if we got a signal, not any
                        # other condition.
                        stop_reason = thread.GetStopReason()
                        if stop_reason != lldb.eStopReasonSignal:
                            process.Continue()

                        sig = thread.GetStopReasonDataAtIndex(1)
                        if sig not in self.sigstocatch:
                            process.Continue()

                        cgcrash = CGCrash()

                        for frame in thread:
                            if frame:
                                cgframe = CGFrame()
                                cgfunction = CGFunction()
                                function = frame.GetFunction()
                                if function:
                                    fargs = frame.GetVariables(True, False, False,
                                            False)
                                    cgfunction.SetType(function.GetType().GetName())
                                    cgfunction.SetName(function.GetName())

                                    for arg in fargs:
                                        cgfunction.AddArg(arg.GetTypeName(),
                                                arg.GetName(), arg.GetValue())


                                    register_list = frame.GetRegisters()

                                    cgframe.SetRegisters(register_list)
                                    cgframe.SetFunction(cgfunction)
                                    cgcrash.AddFrame(cgframe)



                        self.crashes.append(cgcrash)

                        process.Kill()
                        return
                elif state == lldb.eStateExited:
                    print 'No crashes observed in the process'
                else:
                    print 'Unexpected process state: {}'.format(debugger.StateAsCString(state))
                    process.Kill()
                process.Continue()

    def StdoutDump(self):
        for crash in self.crashes:
            frames = crash.GetBacktrace()
            for frame in frames:
                cgfunc = frame.GetFunction()
                ftype = cgfunc.GetType()
                fname = cgfunc.GetName()
                args = cgfunc.GetArgs()
                print_str = "{} {}(".format(ftype, fname)

                for argname, (argtype, argvalue) in args.iteritems():
                    print_str = print_str + "{} {} = {}, ".format(argtype,
                            argname, argvalue)

                print_str = print_str[0:-2]
                print_str = print_str + ")"

                print print_str

    def JsonDump(self):
        return

if __name__ == '__main__':
    cgdb = CGDebugger()
    cgdb.Run()
    cgdb.StdoutDump()
