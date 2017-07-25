#!/usr/local/bin/python

import lldb
import os
import sys
import signal

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
                stop_reason = thread.GetStopReason()
                if stop_reason != lldb.eStopReasonSignal:
                    process.Continue()

                sig = thread.GetStopReasonDataAtIndex(1)
                if sig != signal.SIGSEGV:
                    process.Continue()

                if thread:
                    print thread

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
