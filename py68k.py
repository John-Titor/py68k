#!/usr/bin/env python3
#
# A M68K emulator for development purposes
#

import sys
from pathlib import Path
import argparse
import curses
import importlib

import emulator
import device
import deviceConsole


def run_emu(stdscr, target, args):
    # get an emulator
    emu = target.configure(args)

    # attach the console to the emulator
    deviceConsole.Console.stdscr = stdscr
    emu.add_device(args, deviceConsole.Console)

    # run some instructions
    emu.run()
    emu.finish()
    return emu.fatal_info()


# Parse commandline arguments
parser = argparse.ArgumentParser(description='m68k emulator',
                                 add_help=False,
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--help',
                    action='store_true',
                    help='print this help')

actiongroup = parser.add_mutually_exclusive_group(required=True)
actiongroup.add_argument('--target',
                         type=str,
                         default='none',
                         metavar='TARGET',
                         help='target to emulate')
actiongroup.add_argument('--list-targets',
                         action='store_true',
                         help='list available targets')

(args, _) = parser.parse_known_args()

if args.list_targets:
    p = Path("targets");
    for module in p.glob("*.py"):
        print(f"    {module.stem}")
    sys.exit(0)

if args.target is not None:
    try:
        target = importlib.import_module("targets." + args.target)
        emulator.Emulator.add_arguments(parser)
        deviceConsole.Console.add_arguments(parser)
        device.device.add_arguments(parser)
        target.add_arguments(parser)

    except ModuleNotFoundError as e:
        print(f"unsupported target: {args.target}, try --list-targets")
        sys.exit(1)

    except Exception:
        raise

if args.help is True:
    parser.print_help()
    sys.exit(0)

args = parser.parse_args()

print(curses.wrapper(run_emu, target, args))
