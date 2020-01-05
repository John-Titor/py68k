#!/usr/bin/env python3
#
# A M68K emulator for development purposes
#

import argparse
import curses
import importlib

import emulator
import device

def configure(args, stdscr):
    try:
        target_module = importlib.import_module("targets." + args.target)
    except ModuleNotFoundError as e:
        raise RuntimeError(f"unsupported target: {args.target}")
    except:
        raise

    emu = target_module.configure(args)

    import deviceConsole
    deviceConsole.Console.stdscr = stdscr
    emu.add_device(args, deviceConsole.Console)

    return emu


def run_emu(stdscr, args):
    # get an emulator
    emu = configure(args, stdscr)

    # set tracing options
    if args.trace_memory or args.trace_everything:
        emu.trace_enable('memory')
    for i in args.trace_read_trigger:
        emu.trace_enable('read-trigger', i)
    for i in args.trace_write_trigger:
        emu.trace_enable('write-trigger', i)
    if args.trace_instructions or args.trace_everything:
        emu.trace_enable('instructions')
    for i in args.trace_instruction_trigger:
        emu.trace_enable('instruction-trigger', i)
    if args.trace_jumps or args.trace_everything:
        emu.trace_enable('jumps')
    if args.trace_exceptions or args.trace_everything:
        emu.trace_enable('exceptions')
    for i in args.trace_exception:
        emu.trace_enable('exception', i)
    if args.trace_cycle_limit > 0:
        emu.trace_enable('trace-cycle-limit', args.trace_cycle_limit)
    if args.trace_check_PC_in_text or args.trace_everything:
        emu.trace_enable('check-pc-in-text')

    # run some instructions
    emu.run(args.cycle_limit)

    emu.finish()
    return emu.fatal_info()


# Parse commandline arguments
parser = argparse.ArgumentParser(description='m68k emulator')

parser.add_argument('--target',
                    type=str,
                    default='none',
                    help='target machine, one of simple, tiny68k')
parser.add_argument('--trace-file',
                    type=str,
                    default='trace.out',
                    help='trace output file')
parser.add_argument('--cycle-limit',
                    type=int,
                    default=float('inf'),
                    metavar='CYCLES',
                    help='stop the emulation after CYCLES machine cycles')
parser.add_argument('--trace-everything',
                    action='store_true',
                    help='enable all tracing options')
parser.add_argument('--trace-memory',
                    action='store_true',
                    help='enable memory tracing at startup')
parser.add_argument('--trace-read-trigger',
                    action='append',
                    type=str,
                    default=list(),
                    metavar='ADDRESS-or-NAME',
                    help='enable memory tracing when ADDRESS-or-NAME is read')
parser.add_argument('--trace-write-trigger',
                    action='append',
                    type=str,
                    default=list(),
                    metavar='ADDRESS-or-NAME',
                    help='enable memory tracing when ADDRESS-or-NAME is written')
parser.add_argument('--trace-instructions',
                    action='store_true',
                    help='enable instruction tracing at startup (implies --trace-jumps)')
parser.add_argument('--trace-instruction-trigger',
                    action='append',
                    type=str,
                    default=list(),
                    metavar='ADDRESS-or-NAME',
                    help='enable instruction and jump tracing when execution reaches ADDRESS-or-NAME')
parser.add_argument('--trace-jumps',
                    action='store_true',
                    help='enable branch tracing at startup')
parser.add_argument('--trace-exceptions',
                    action='store_true',
                    help='enable tracing all exceptions at startup')
parser.add_argument('--trace-exception',
                    type=int,
                    action='append',
                    default=list(),
                    metavar='EXCEPTION',
                    help='enable tracing for EXCEPTION at startup (may be specified more than once)')
parser.add_argument('--trace-io',
                    action='store_true',
                    help='enable tracing of I/O space accesses')
parser.add_argument('--trace-cycle-limit',
                    type=int,
                    default=0,
                    metavar='CYCLES',
                    help='stop the emulation after CYCLES following an instruction or memory trigger')
parser.add_argument('--trace-check-PC-in-text',
                    action='store_true',
                    help='when tracing instructions, stop if the PC lands outside the text section')
parser.add_argument('--debug-device',
                    type=str,
                    default='',
                    help='comma-separated list of devices to enable debug tracing, \'device\' to trace device framework')
parser.add_argument('--diskfile',
                    type=str,
                    default=None,
                    help='disk image file')
parser.add_argument('image',
                    type=str,
                    default='none',
                    help='executable to load')
args = parser.parse_args()

print(curses.wrapper(run_emu, args))
