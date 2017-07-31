#!/usr/local/bin/python

"""
"""

import argparse
import collections
import os
import signal
import sys

import lldb
import json
from enum import Enum


def jcrash(o):
    if isinstance(o, CGCrash):
        return [o.name, o.frames]
    elif isinstance(o, CGFrame):
        return [o.function, o.registers, str(o.line_entry)]
    elif isinstance(o, CGFunction):
        return [str(o.function_type), o.name, o.args]
    elif isinstance(o, CGRegister):
        return [str(o.type), str(o.name), str(o.value)]


class CGRegister:
    def __init__(self, rtype, name, val):
        self.type = rtype
        self.name = name
        self.value = val

    @classmethod
    def from_frame(cls, frame):
        return [CGRegister(val.GetName(),
                           reg.GetName(),
                           reg.GetValue())
                for val in frame.GetRegisters()
                for reg in val
                if reg.GetValue() is not None]


class CGFrameEntryType(Enum):
    UNDEFINED = 0
    FUNCTION = 1
    SYMBOL = 2


class CGFrameEntry:
    def __init__(self,
                 function_type="",
                 name="",
                 frame_entry_type=CGFrameEntryType.UNDEFINED):
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
        CGFrameEntry.__init__(self,
                              function_type,
                              name,
                              CGFrameEntryType.FUNCTION)
        if args is None:
            args = {}
        self.args = args

    def add_arg(self, arg):
        self.args[arg.GetName()] = self.CGArg(arg.GetTypeName(),
                                              arg.GetValue())

    def get_arg(self, name):
        return self.args[name]

    def set_arg(self, arg_type, name, val):
        if self.args[name]:
            self.args[name] = self.CGArg(arg_type, val)

    @classmethod
    def from_frame(cls, frame):
        func = frame.GetFunction()
        if not func:
            return None
        fargs = frame.GetVariables(True,
                                   False,
                                   False,
                                   False)
        cgfunction = cls(function_type=func.GetType(),
                         name=func.GetName())
        for arg in fargs:
            cgfunction.add_arg(arg)
        return cgfunction


class CGSymbol(CGFrameEntry):
    """
    This is currently unused, but we might wish to abstract it away using this
    method later on.
    """
    def __init__(self, function_type="", name=""):
        CGFrameEntry.__init__(self,
                              function_type,
                              name,
                              CGFrameEntryType.SYMBOL)


class CGFrame:
    def __init__(self, function=None, registers=None, line_entry=""):
        if registers is None:
            self.registers = []

        self.function = function
        self.line_entry = line_entry

    def AddRegister(self, reg):
        self.registers.append(reg)

    @classmethod
    def from_frame(cls, frame):
        cgfunction = CGFunction.from_frame(frame)
        if not cgfunction:
            return None
        cgframe = cls(function=cgfunction,
                      line_entry=frame.GetLineEntry())
        cgframe.AddRegister(CGRegister.from_frame(frame))
        return cgframe


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

    def add_frame(self, frame):
        cgframe = CGFrame.from_frame(frame)
        if not cgframe:
            return
        self.frames.append(cgframe)

    def get_backtrace(self):
        return self.frames

    @classmethod
    def from_thread(cls, thread):
        crash = cls(thread=thread)
        for frame in thread:
            if not frame:
                continue
            crash.add_frame(frame)
        return crash


class CGDebugger:
    def __init__(self,
                 binary_path='./a.out',
                 inpath='out',
                 filter_list=None,
                 sigstocatch=(signal.SIGSEGV, signal.SIGABRT)):
        # We hook into lldb here
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        self.inpath = inpath
        self.test_cases = []

        if filter_list is None:
            filter_list = [""]
        self.filter_list = filter_list

        for root, dirs, files in os.walk(self.inpath):
            for fname in files:
                full_path = os.path.join(root, fname)
                for filt in filter_list:
                    if filt not in full_path:
                        continue
                    self.test_cases.append(full_path)

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
            state = process.GetState()
            if state == lldb.eStateExited:
                print 'No crashes observed in the process given {}'.format(tc)
                process.Destroy()
            elif state != lldb.eStateStopped:
                print 'Unexpected process state: {}'.format(
                    self.debugger.StateAsCString(state))
                process.Kill()
            else:
                thread = process.GetThreadAtIndex(0)
                if not thread:
                    return
                # We only want to examine if we got a signal, not any
                # other condition.
                stop_reason = thread.GetStopReason()
                if stop_reason != lldb.eStopReasonSignal:
                    process.Continue()
                sig = thread.GetStopReasonDataAtIndex(1)
                if sig not in self.sigstocatch:
                    process.Continue()

                self.crashes.append(CGCrash.from_thread(thread))
                process.Kill()

    def stdout_dump(self):
        for crash in self.crashes:
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
            print '\n'

    def json_dump(self, dst):
        if dst == sys.stdout:
            json.dump(self.crashes,
                      sys.stdout,
                      sort_keys=True,
                      indent=2,
                      separators=(',', ': '),
                      default=jcrash)
        else:
            with open(dst, "w+") as f:
                json.dump(self.crashes,
                          f,
                          sort_keys=True,
                          indent=2,
                          separators=(',', ': '),
                          default=jcrash)
        return


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--filter", default='')
    parser.add_argument("--mode", choices=['stdout', 'json'], default='stdout')
    parser.add_argument("--out", default=sys.stdout)
    parser.add_argument("--testcase-path", required=True)
    args = parser.parse_args()

    cgdb = CGDebugger(args.binary,
                      args.testcase_path,
                      [f for f in args.filter.split(',') if f])
    cgdb.run()

    if args.mode == "stdout":
        cgdb.stdout_dump()
    elif args.mode == "json":
        cgdb.json_dump(args.out)
