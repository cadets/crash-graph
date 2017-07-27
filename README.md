# Crash Graph

Crash Graph is built as a tool that inspects inputs to a given binary and
collects the crash data upon the crash of that binary. It supports filtering of
directories that the user wishes to traverse and supports both summarized format
outputted to `stdout`, as well as structured json output meant to be
post-processed.

### Usage ###

Crash Graph is a single python file that expects two core inputs, the path to
the binary and the directory root containing all of the test cases. The simplest
way to run the software is to have an `a.out` in the current working directory,
as well as an `out` directory containing the test cases. With that, running

```
./create_crashgraph.py
```

will format the output and summarize it on `stdout`.

The following flags are supported:
	- [--binary <BINARY>] - path to the binary to examine
	- [--testcase-path <PATH>] - path to the directory containing the test
	  cases
	- [--mode <MODE>] - mode of operation (stdout or json)
	- [--out <OUT>] - path to the output json file. This only works in json
	  mode
	- [--filter <comma separated FILTER>] - should you only wish to include
	  subdirectories and files that contain a certain string within them,
	  this option provides a way to do so by separating values by commas
	- [-h] - display help

### Saved information ###

Crash Graph saves a large amount of information of a crash. For each crash, the
following information is stored:
	- The stack trace that contains:
		- Function information
			- Name
			- Type
			- Argument information:
				- Name
				- Type
				- Value
		- All non-NULL registers
			- General purpose
			- Floating point
	- The offending thread information (TODO)

### Output ###

The output that is displayed on `stdout` is fairly straightforward to understand
and follows the pattern:

```
fn_type (arg1_type, arg2_type, ..., argn_type) fn_name(arg1_type arg1_val, ...,
argn_type, argn_val) -> /path/to/file + line number information
```

TODO: json output
