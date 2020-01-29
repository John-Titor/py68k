#!/usr/bin/env python3
#
# A M68K emulator for development purposes
#

import sys
import argparse
import importlib
from pathlib import Path

from emulator import Emulator
from device import Device, RootDevice
from console import Console


# Parse commandline arguments
parser = argparse.ArgumentParser(description='m68k emulator',
                                 add_help=False,
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                 fromfile_prefix_chars='@',
                                 epilog='Read options from a file: @CONFIG-FILENAME')
parser.add_argument('--help',
                    action='store_true',
                    help='print this help')

actiongroup = parser.add_mutually_exclusive_group()
actiongroup.add_argument('--target',
                         type=str,
                         default='none',
                         metavar='TARGET',
                         help='target to emulate')
actiongroup.add_argument('--list-targets',
                         action='store_true',
                         help='list available targets')
actiongroup.add_argument('--console-server',
                         action='store_true',
                         help='run the interactive console server')

(args, _) = parser.parse_known_args()

if args.list_targets:
    p = Path('targets')
    for module in p.glob('*.py'):
        print(f'    {module.stem}')
    sys.exit(0)

if args.console_server:
    Console().run()
    sys.exit(0)

if args.target is not None:
    target = importlib.import_module('targets.' + args.target)
    Emulator.add_arguments(parser)
    Device.add_arguments(parser)
    RootDevice.add_arguments(parser)
    target.add_arguments(parser)

if args.help is True:
    parser.print_help()
    sys.exit(0)

# configure the emulator
args = parser.parse_args()
emu = target.configure(args)

# run some instructions
emu.run()
emu.finish()
print(emu.fatal_info())
