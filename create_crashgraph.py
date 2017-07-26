#!/usr/local/bin/python

"""
"""

import collections
import os
import signal

import lldb
from enum import Enum


CGRegister = collections.namedtuple("CGRegister", ['name', 'num_children', 'value'])


class CGFrameEntryType(Enum):
    FUNCTION = 1
    SYMBOL = 2


class CGFrameEntry:
    def __init__(self,
                 function_type="",
                 name="",
                 frame_entry_type=CGFrameEntryType.FUNCTION):
        self.name = name
        self.frame_entry_type = frame_entry_type
        self.function_type = function_type


class CGFunction(CGFrameEntry):
    CGArg = collections.namedtuple("CGArg", ['atype', 'val'])

    """
    Currently, we only use CGFunction as a type of CGFrameEntry, CGSymbol is
    unused.

    We keep a dictionary of arguments in the function so that we can access
    their values with their name in the scope of one frame.
    """
    def __init__(self, function_type="", name="", args=None):
        CGFrameEntry.__init__(self, function_type, name)
        if args is None:
            args = {}
        self.args = args

    def add_arg(self, arg_type, name, val):
        self.args[name] = self.CGArg(arg_type, val)

    def get_arg(self, name):
        return self.args[name]

    def set_arg(self, arg_type, name, val):
        if self.args[name]:
            self.args[name] = self.CGArg(arg_type, val)


class CGSymbol(CGFrameEntry):
    """
    This is currently unused, but we might wish to abstract it away using this
    method later on.
    """
    def __init__(self, function_type="", name=""):
        CGFrameEntry.__init__(self, function_type, name, CGFrameEntryType.SYMBOL)


CGFrame = collections.namedtuple("CGFrame", ['function', 'registers', 'line_entry'])


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

    def get_backtrace(self):
        return self.frames


class CGDebugger:
    def __init__(self,
                 binary_path='./a.out',
                 inpath='out',
                 sigstocatch=(signal.SIGSEGV, signal.SIGABRT)):
        # We hook into lldb here
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        self.inpath = inpath
        self.test_cases = []

        for root, dirs, files in os.walk(self.inpath):
            for fname in files:
                self.test_cases.append(os.path.join(root, fname))

        # Create the debugging target and identify which signals we want to
        # catch
        self.target = self.debugger.CreateTarget(binary_path)
        self.sigstocatch = sigstocatch

        self.crashes = []

    def run(self):
        if not self.target:
            return
        
        # Iterate over the test cases
        for tc in self.test_cases:
            error = lldb.SBError()
            process = self.target.Launch(self.debugger.GetListener(),
                                         None,
                                         None,
                                         tc,
                                         None,
                                         None,
                                         os.getcwd(),
                                         0,
                                         False,
                                         error)
            if not process:
                return
            cgcrash = CGCrash()

            state = process.GetState()
            if state == lldb.eStateExited:
                print 'No crashes observed in the process'
            elif state != lldb.eStateStopped:
                print 'Unexpected process state: {}'.format(self.debugger.StateAsCString(state))
                process.Kill()
            else:
                thread = process.GetThreadAtIndex(0)
                if not thread:
                    return
                cgcrash.thread = thread

                # We only want to examine if we got a signal, not any
                # other condition.
                stop_reason = thread.GetStopReason()
                if stop_reason != lldb.eStopReasonSignal:
                    process.Continue()
                sig = thread.GetStopReasonDataAtIndex(1)
                if sig not in self.sigstocatch:
                    process.Continue()

                for frame in thread:
                    if not frame:
                        continue
                    func = frame.GetFunction()
                    if not func:
                        continue
                    fargs = frame.GetVariables(True,
                                               False,
                                               False,
                                               False)
                    cgfunction = CGFunction(function_type=func.GetType(),
                                            name=func.GetName())
                    for arg in fargs:
                        cgfunction.add_arg(arg.GetTypeName(),
                                           arg.GetName(),
                                           arg.GetValue())
                    cgframe = CGFrame(cgfunction,
                                      frame.GetRegisters(),
                                      frame.GetLineEntry())
                    cgcrash.add_frame(cgframe)
                self.crashes.append(cgcrash)
                process.Kill()
                continue
            process.Continue()

    def stdout_dump(self):
        for crash in self.crashes:
            print crash.thread.GetProcess()
            print crash.thread
            for frame in crash.get_backtrace():
                cgfunc = frame.function
                arg_str = ", ".join(["{} {} = {}".format(arg.atype,
                                                         name,
                                                         arg.val)
                                     for name, arg
                                     in cgfunc.args.iteritems()])
                print "{} {}({}) -> {}".format(cgfunc.function_type,
                                         cgfunc.name,
                                         arg_str,
                                         frame.line_entry)

    def json_dump(self):
        return


if __name__ == '__main__':
    cgdb = CGDebugger()
    cgdb.run()
    cgdb.stdout_dump()
