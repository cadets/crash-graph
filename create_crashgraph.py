#!/usr/local/bin/python

# Copyright (c) 2017 Domagoj Stolfa, Thomas Bytheway
# All rights reserved.
# 
# This software was developed by BAE Systems, the University of Cambridge
# Computer Laboratory, and Memorial University under DARPA/AFRL contract
# FA8650-15-C-7558 ("CADETS"), as part of the DARPA Transparent Computing
# (TC) research program.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
   # notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
   # notice, this list of conditions and the following disclaimer in the
   # documentation and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

"""
"""

import argparse
import collections
import os
import signal
import sys
import logging
import time
import multiprocessing

import lldb
import json
from enum import Enum

# TODO: This should be made a command line argument (--verbose)
VERBOSE = True
TIMEOUT = 5
log = None


class CGRegister:
    def __init__(self, rtype, name, val):
        self.type = rtype
        self.name = name
        self.value = val

    def as_json(self):
        return {'type': str(self.type),
                'name': str(self.name),
                'value': str(self.value)}

    @classmethod
    def from_frame(cls, frame):
        return [CGRegister(str(val.GetName()),
                           str(reg.GetName()),
                           str(reg.GetValue()))
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


class CGArg:
    def __init__(self, atype, val):
        self.atype = atype
        self.val = val

    def as_json(self):
        return {'atype': self.atype,
                'val': self.val}


class CGFunction(CGFrameEntry):
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
        self.args[arg.GetName()] = CGArg(arg.GetTypeName(),
                                         arg.GetValue())

    def get_arg(self, name):
        return self.args[name]

    def set_arg(self, arg_type, name, val):
        if self.args[name]:
            self.args[name] = CGArg(arg_type, val)

    def as_json(self):
        return {'function_type': str(self.function_type),
                'name': self.name,
                'args': self.args}

    @classmethod
    def from_frame(cls, frame):
        func = frame.GetFunction()
        if not func:
            return None
        fargs = frame.GetVariables(True,
                                   False,
                                   False,
                                   False)
        cgfunction = cls(function_type=str(func.GetType()),
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


class CGThread:
    def __init__(self, tid=0):
        self.tid = tid

    @classmethod
    def from_thread(cls, thread):
        tid_int = long(thread.GetThreadID())
        cgthread = cls(tid=tid_int)

        return cgthread


class CGFrame:
    def __init__(self, function=None, registers=None, line_entry=""):
        if registers is None:
            self.registers = []

        self.function = function
        self.line_entry = line_entry

    def AddRegister(self, reg):
        self.registers.append(reg)

    def as_json(self):
        return {'function': self.function,
                'registers': self.registers,
                'line_entry': str(self.line_entry)}

    @classmethod
    def from_frame(cls, frame):
        cgfunction = CGFunction.from_frame(frame)
        if not cgfunction:
            return None
        cgframe = cls(function=cgfunction,
                      line_entry=str(frame.GetLineEntry()))
        cgframe.AddRegister(CGRegister.from_frame(frame))
        return cgframe


class CGCrash:
    """
    We use CGCrash to keep the information of a full crash. It contains the
    backtrace stack, which we pop off entry by entry until it's empty.

    We also record the registers for each frame inside of this class with the
    purpose of more detailed analysis later on.
    """
    def __init__(self, frames=None, thread=None, name="GenericCrashName", tc=""):
        if frames is None:
            frames = []
        self.frames = frames
        self.thread = thread
        self.name = name
        self.tc = tc

    def add_frame(self, frame):
        cgframe = CGFrame.from_frame(frame)
        if not cgframe:
            return
        self.frames.append(cgframe)

    def get_backtrace(self):
        return self.frames

    def as_json(self):
        return {'name': self.name,
                'input_file': self.tc,
                'frames': self.frames}

    @classmethod
    def from_thread(cls, thread, tc):
        cgthread = CGThread.from_thread(thread)
        if not cgthread:
            return None
        crash = cls(thread=cgthread, tc=tc)
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

        self.test_cases = []
        self.mpqueue = None

        if filter_list is None:
            filter_list = [""]
        self.filter_list = filter_list

        for root, dirs, files in os.walk(inpath):
            for fname in files:
                full_path = os.path.join(root, fname)
                for filt in filter_list:
                    if filt not in full_path:
                        break
                    if "README" in full_path:
                        break
                else:
                    abs_path = os.path.abspath(full_path)
                    self.test_cases.append(abs_path)

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
            self.mpqueue = multiprocessing.Queue()
            if self.mpqueue is None:
                log.error("Failed to create the queue")
                return

            proc = multiprocessing.Process(target=self.run_tc, args=(tc,))
            proc.start()

            proc.join(TIMEOUT)
            proc.terminate()
            proc.join()

            if not self.mpqueue.empty():
                self.crashes.append(self.mpqueue.get(False))
            else:
                log.info("No crash observed in {}".format(tc))

    def run_tc(self, tc=None):
        if tc is None:
            return
        error = lldb.SBError()
        log.info("Testcase: {}".format(tc))
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
            log.error("Failed getting process")
            return
        state = process.GetState()
        log.info("State: {}".format(state))
        if state == lldb.eStateExited:
            process.Destroy()
        elif state != lldb.eStateStopped:
            print 'Unexpected process state: {}'.format(
                self.debugger.StateAsCString(state))
            process.Destroy()
        else:
            thread = process.GetThreadAtIndex(0)
            if not thread:
                log.info("Failed getting thread")
                return
            # We only want to examine if we got a signal, not any
            # other condition.
            stop_reason = thread.GetStopReason()
            log.info("Stop reason: {}".format(stop_reason))
            if stop_reason != lldb.eStopReasonSignal:
                process.Continue()
            sig = thread.GetStopReasonDataAtIndex(1)
            if sig not in self.sigstocatch:
                process.Continue()

            log.info("Creating a new crash")
            crash = CGCrash.from_thread(thread, tc)
            self.mpqueue.put(crash, False)
            log.info("Crash: {}".format(crash))
            process.Destroy()

    def stdout_dump(self):
        for crash in self.crashes:
            print "Crash caused by: {}".format(crash.tc)
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
        def jcrash(o):
            if hasattr(o, 'as_json'):
                return o.as_json()
        json.dump(self.crashes,
                  dst,
                  sort_keys=True,
                  indent=2,
                  separators=(',', ': '),
                  default=jcrash)


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    log = logging.getLogger("CrashGraph")

    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--filter", default='')
    parser.add_argument("--mode", choices=['stdout', 'json'], default='stdout')
    parser.add_argument("--out", type=argparse.FileType('w+'),
                        default=sys.stdout)
    parser.add_argument("--testcase-path", required=True)
    args = parser.parse_args()

    log.info("Initializing the debugger")
    cgdb = CGDebugger(args.binary,
                      args.testcase_path,
                      [f for f in args.filter.split(',') if f])

    cgdb.run()

    if args.mode == "stdout":
        cgdb.stdout_dump()
    elif args.mode == "json":
        cgdb.json_dump(args.out)
    args.out.close()
