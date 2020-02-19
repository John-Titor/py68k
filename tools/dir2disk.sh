#!/bin/sh
#
# Make a single-partition FAT16 disk image with the contents of a folder.
#
# macOS only, since the DiskImages framework does all the heavy lifting.
#

function usage() {
    if [ ! -z '$1' ]; then
        echo "\nERROR: $1\n"
    fi
    echo "usage: $0 [-o] [-p <pad MiB> | -s <size MiB>] <output file> <input directory>\n"
    echo "  creates a FAT16 disk image in <output file> containing the files in <input directory>"
    echo "  -o             OK to replace <output file> if it exists"
    echo "  -p <pad MiB>   add padding to filesystem (min 5MiB)"
    echo "  -s <size MiB>  set filesystem size (must be large enough for files + 5MiB)"
    exit 1
}

overwrite=1
padsize=5
fixsize=0

args=`getopt op:s: $*`
if [ $? != 0 ]; then
    usage "invalid option(s)"
fi
set -- $args
for i; do
    case "$i" in
        -o ) 
            overwrite=0
            shift;;
        -p )
            padsize=$2
            shift; shift;;
        -s )
            fixsize=$2
            shift; shift;;
        -- )
            shift; break;;
    esac
done

if [ ! $# -eq 2 ]; then
    usage "missing argument(s)"
fi
if [ -e $1 ]; then
    if [ -f $1 ]; then
        if [ ! $overwrite ]; then
            usage "file $1 already exists"
        fi
        rm -f $1
    else
        usage "$1 exists and is not a file"
    fi
fi
if [ ! -d $2 ]; then
    usage "$2 not a directory or does not exist"
fi

dirsize=`du -mLs $2 | cut -f 1`

if [ $fixsize -gt 0 ]; then
    if [ $fixsize -lt $dirsize ]; then
        usage "specified size $fixsize MiB too small, need $dirsize MiB"
    fi
elif [ $padsize -gt 0 ]; then
    if [ $padsize -lt 5 ]; then
        usage "padding size less than 5 MiB not recommended"
    fi
    fixsize=`expr $dirsize + $padsize`
else
    usage "must specify a non-zero padding size, or a fixed size"
fi

echo "creating $fixsize MiB image $1 with contents from $2..."
hdiutil create -megabytes $fixsize -layout MBRSPUD -fs "MS-DOS FAT16" -format UDIF -srcfolder $2 $1
