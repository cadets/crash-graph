#!/usr/local/bin/python

"""
"""

import lldb
import os
import signal
from enum import Enum


class CGRegister:
    def __init__(self, name="", num_children=0, value=0):
        self.name = name
        self.num_children = num_children
        self.value = value

    def get_name(self):
        return self.name

    def get_num_children(self):
        return self.num_children

    def get_value(self):
        return self.value


class CGFrameEntryType(Enum):
    FUNCTION = 1
    SYMBOL = 2


class CGFrameEntry:
    def __init__(self, ftype="", name="", fetype=CGFrameEntryType.FUNCTION):
        self.name = name
        self.type = fetype  # Frame entry type
        self.ftype = ftype  # Function type

    def set_name(self, name):
        self.name = name

    def get_name(self):
        return self.name

    def set_type(self, fetype):
        self.type = fetype

    def get_type(self):
        return self.type


class CGFunction(CGFrameEntry):
    """
    Currently, we only use CGFunction as a type of CGFrameEntry, CGSymbol is
    unused.

    We keep a dictionary of arguments in the function so that we can access
    their values with their name in the scope of one frame.
    """
    def __init__(self, ftype="", name="", args=None):
        CGFrameEntry.__init__(self, ftype, name)
        if args is None:
            args = {}
        self.args = args

    def set_args(self, args):
        self.args = args

    def add_arg(self, argtype, argname, argval):
        self.args[argname] = (argtype, argval)

    def get_arg(self, argname):
        return self.args[argname]

    def get_arg_value(self, argname):
        return self.args[argname][0]

    def get_arg_type(self, argname):
        return self.args[argname][1]

    def number_of_args(self):
        return len(self.args)

    def set_arg(self, argtype, argname, argval):
        if self.args[argname]:
            self.args[argname] = (argtype, argval)

    def get_args(self):
        return self.args

    def get_type(self):
        return self.ftype


class CGSymbol(CGFrameEntry):
    """
    This is currently unused, but we might wish to abstract it away using this
    method later on.
    """
    def __init__(self, ftype="", name=""):
        CGFrameEntry.__init__(self, ftype, name, CGFrameEntryType.SYMBOL)


class CGFrame:
    def __init__(self, cgfun=None, cgregs=None):
        self.cgfun = cgfun
        self.cgregs = cgregs

    def set_registers(self, cgregs):
        self.cgregs = cgregs

    def get_registers(self):
        return self.cgregs

    def set_function(self, cgfun):
        self.cgfun = cgfun

    def get_function(self):
        return self.cgfun


class CGCrash:
    """
    We use CGCrash to keep the information of a full crash. It contains the
    backtrace stack, which we pop off entry by entry until it's empty.

    We also record the registers for each frame inside of this class with the
    purpose of more detailed analysis later on.
    """
    def __init__(self, frames=None, thread=None, name="GenericCrashName"):
        if frames is None:
            frames = []
        self.frames = frames
        self.thread = thread
        self.name = name

    def add_frame(self, cgframe):
        self.frames.append(cgframe)

    def set_thread(self, thread):
        self.thread = thread

    def get_thread(self):
        return self.thread

    def get_backtrace(self):
        return self.frames


class CGDebugger:
    def __init__(self,
                 binary_path='./a.out',
                 indata='out',
                 sigstocatch=(signal.SIGSEGV, signal.SIGABRT)):
        # We hook into lldb here
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        self.indata = indata

        # Create the debugging target and identify which signals we want to
        # catch
        self.target = self.debugger.CreateTarget(binary_path)
        self.sigstocatch = sigstocatch

        self.crashes = []

    def run(self):
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
                        cgcrash.set_thread(thread)
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
                                func = frame.GetFunction()
                                if func:
                                    fargs = frame.GetVariables(True,
                                                               False,
                                                               False,
                                                               False)
                                    cgfunction.set_type(func.GetType().GetName())
                                    cgfunction.set_name(func.GetName())

                                    for arg in fargs:
                                        cgfunction.add_arg(arg.get_type_name(),
                                                           arg.get_name(),
                                                           arg.get_value())

                                    register_list = frame.get_registers()

                                    cgframe.set_registers(register_list)
                                    cgframe.set_function(cgfunction)
                                    cgcrash.add_frame(cgframe)

                        self.crashes.append(cgcrash)

                        process.Kill()
                        return
                elif state == lldb.eStateExited:
                    print 'No crashes observed in the process'
                else:
                    print 'Unexpected process state: {}'.format(self.debugger.StateAsCString(state))
                    process.Kill()
                process.Continue()

    def stdout_dump(self):
        for crash in self.crashes:
            frames = crash.GetBacktrace()
            for frame in frames:
                cgfunc = frame.GetFunction()
                ftype = cgfunc.GetType()
                fname = cgfunc.GetName()
                args = cgfunc.GetArgs()
                arg_str = ", ".join(["{} {} = {}".format(name, atype, val)
                                     for name, (atype, val) in args.iteritems()])
                print "{} {}({})".format(ftype, fname, arg_str)

    def json_dump(self):
        return


if __name__ == '__main__':
    cgdb = CGDebugger()
    cgdb.run()
    cgdb.stdout_dump()
