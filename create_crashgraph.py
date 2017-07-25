#!/usr/local/bin/python

import lldb
import os
import sys
import signal

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

class CGCrash:
    def __init__(self, backtrace=None, registers=None):
        self.backtrace = backtrace
        self.registers = registers

    def SetRegisters(self, registers):
        self.registers = registers

    def SetBacktrace(self, backtrace):
        self.backtrace = backtrace

    def GetRegisters(self):
        return self.registers

    def GetBacktrace(self):
        return self.backtrace

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

    def disassemble(self, instructions):
        for i in instructions:
            print i

    def Run(self):
        if self.target:
            # Launch the process
            process = self.target.LaunchSimple(None, None, os.getcwd())
            if process:
                print process
                state = process.GetState()
                if state == lldb.eStateStopped:
                    thread = process.GetThreadAtIndex(0)
                    
                    if thread:
                        print thread

                        # We only want to examine if we got a signal, not any
                        # other condition.
                        stop_reason = thread.GetStopReason()
                        if stop_reason != lldb.eStopReasonSignal:
                            process.Continue()

                        sig = thread.GetStopReasonDataAtIndex(1)
                        if sig not in self.sigstocatch:
                            process.Continue()

                        frame = thread.GetFrameAtIndex(0)
                        if frame:
                            function = frame.GetFunction()
                            if function:
                                print function
                                instructions = function.GetInstructions(self.target)
                                self.disassemble(instructions)
                            else:
                                symbol = frame.GetSymbol()
                                if symbol:
                                    print symbol
                                    instructions = symbol.GetInstructions(self.target)
                                    self.disassemble(instructions)

                            register_list = frame.GetRegisters()
                            print 'Frame registers (size of register set = {}):'.format(register_list.GetSize())
                            for value in register_list:
                                print "{} (number of children = {}):".format(value.GetName(), value.GetNumChildren())
                                for child in value:
                                    print 'Name: {} Value: {}'.format(child.GetName(), child.GetValue())

                process.Continue()
            elif state == lldb.eStateExited:
                print 'No crashes observed in the process'
            else:
                print 'Unexpected process state: {}'.format(debugger.StateAsCString(state))
                process.Kill()

if __name__ == '__main__':
    cgdb = CGDebugger()
    cgdb.Run()
