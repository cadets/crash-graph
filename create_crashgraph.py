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
    # Create the debugger
    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)

    # FIXME: We currently set our target as a.out for testing purposes, this
    # should however be absolutely arbitrary (parhaps a path to the input test
    # cases and binary?
    target = debugger.CreateTarget('./a.out')

    if target:
        # Launch the traget in the current working directory
        process = target.LaunchSimple(None, None, os.getcwd())
        if process:
            state = process.GetState()
            print process
            # XXX: Currently, we will only check for eStateStopped, as it is
            # unclear to me what eStateCrashed means.
            if state == lldb.eStateStopped:

                # FIXME: Assumption that we are running on one thread (not
                # always true!)
                thread = process.GetThreadAtIndex(0)

                if thread:
                    print thread

                    stop_reason = thread.GetStopReason()
                    # If the stopping reason is not a signal, we just continue
                    # execution
                    if stop_reason != lldb.eStopReasonSignal:
                        process.Continue()

                    sig = thread.GetStopReasonDataAtIndex(1)
                    # Check for SIGSEGV and SIGABRT
                    # XXX: This should probably be written in a more generic
                    # sense?
                    if sig != signal.SIGSEGV or signal.SIGABRT:
                        process.Continue()

                    # Get the frame where we stopped
                    # FIXME: We should walk all of the frames here and down to
                    # the interested one. We are creating a graph, not just a
                    # histogram
                    frame = thread.GetFrameAtIndex(0)
                    if frame:
                        # Get the function that we crashed in
                        function = frame.GetFunction()
                        if function:
                            print function
                            instructions = function.GetInstructions(target)
                            disassemble(instructions)
                        else:
                            # It wasn't a function, attempt the same thing with
                            # a symbol
                            symbol = frame.GetSymbol()
                            if symbol:
                                print symbol
                                instructions = symbol.GetInstructions(target)
                                disassemble(instructions)

                        # Walk the register list
                        registerList = frame.GetRegisters()
                        print 'Frame registers (size of register set = {}):'.format(registerList.GetSize())
                        for value in registerList:
                            print "{} (number of children = {}):".format(value.GetName(), value.GetNumChildren())
                            for child in value:
                                print 'Name: {} Value: {}'.format(child.GetName(), child.GetValue())

                    process.Continue()
            # If we have successfully exited, there should be no crash graph.
            elif state == lldb.eStateExited:
                print "There have been no crashes in the executable"
            else:
                print 'Unexpected process state: {}'.format(debugger.StateAsCString(state))
                process.Kill()
