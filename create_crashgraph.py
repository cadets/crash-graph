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

class CGFunction:
    def __init__(self, name=""):
        self.name = name

class CGNode:
    def __init__(self):
        return
    

def disassemble(instructions):
    for i in instructions:
        print i

if __name__ == '__main__':
    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)

    target = debugger.CreateTarget('./a.out')

    if target:
        process = target.LaunchSimple(None, None, os.getcwd())
        if process:
            state = process.GetState()
            print process
            if state == lldb.eStateCrashed or state == lldb.eStateStopped:
                thread = process.GetThreadAtIndex(0)

                if thread:
                    print thread

                    stop_reason = thread.GetStopReason()
                    if stop_reason != lldb.eStopReasonSignal:
                        process.Continue()

                    sig = thread.GetStopReasonDataAtIndex(1)
                    if sig != signal.SIGSEGV or signal.SIGABRT:
                        process.Continue()
                    frame = thread.GetFrameAtIndex(0)
                    if frame:
                        function = frame.GetFunction()
                        if function:
                            print function
                            instructions = function.GetInstructions(target)
                            disassemble(instructions)
                        else:
                            symbol = frame.GetSymbol()
                            if symbol:
                                print symbol
                                instructions = symbol.GetInstructions(target)
                                disassemble(instructions)

                        registerList = frame.GetRegisters()
                        print 'Frame registers (size of register set = {}):'.format(registerList.GetSize())
                        for value in registerList:
                            print "{} (number of children = {}):".format(value.GetName(), value.GetNumChildren())
                            for child in value:
                                print 'Name: {} Value: {}'.format(child.GetName(), child.GetValue())

                    process.Continue()
            elif state == lldb.eStateExited:
                print "Didn't hit the BP"
            else:
                print 'Unexpected process state: {}'.format(debugger.StateAsCString(state))
                process.Kill()
