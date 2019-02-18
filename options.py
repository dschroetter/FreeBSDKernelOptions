import argparse
import os
import re
from enum import Enum, unique, auto
from subprocess import Popen, PIPE
import shlex
import mmap


@unique
class EntryType(Enum):
    OPTION = auto()


class ArchAutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name


@unique
class Architecture(ArchAutoName):
    ALL = auto()
    AMD64 = auto()
    ARM = auto()
    I386 = auto()
    MIPS = auto()
    PC98 = auto()
    POWERPC = auto()
    RISCV = auto()
    SPARC64 = auto()
    UNKNOWN = auto()


class Option(object):

    def __init__(self, name, arch=Architecture.ALL):
        self.arch = [arch]
        self.file = {}
        self.innotes = set()
        self.default = None
        self.manentries = set()

    def collapse(self):
        """"""

        if (len(self.file) < 2) or (len(self.file) != len(self.arch)) or \
           (sorted(self.file.keys()) != sorted([x.value.lower() for x in self.arch])) or \
           (len(set(self.file.values())) != 1):
            return

        opt_file = set(self.file.values()).pop()
        self.file = {}
        self.file['all'] = opt_file

    def __str__(self):
        """"""

        return ("%d %d %d %d" % (len(self.innotes), len(self.arch), len(self.file), len(self.manentries)))


class OptionList(object):
    """"""

    def __init__(self):
        """"""

        super.__init__(self)


translatable_options = {
    'IPFW_DEFAULT_TO_(ACCEPT|DENY)':
    ['IPFW_DEFAULT_TO_ACCEPT', 'IPFW_DEFAULT_TO_DENY'],
    'geom_map': ['GEOM_MAP']
}


def parse_file(filename, arch, optionlist):

    try:
        with open(filename) as f:
            print('Processing options file %s' % filename)

            for line in f:

                if line[0] == '#' or line[0] == '\n' or line[0] == '\t':
                    continue

                elem = line.split()

                #
                # elem[0] is the name of the option
                # elem[1] is the filename for the option
                #

                if elem[0] not in optionlist.keys():
                    optionlist[elem[0]] = Option(elem[0], arch)
                else:
                    optionlist[elem[0]].arch.append(arch)

                optionlist[elem[0]].file[arch.value.lower()] = elem[1] \
                    if (len(elem) > 1) else ''

    except Exception as e:
        print('Could not find file %s for architecture %s. Architecture removed ?'
              % (filename, arch))

    return optionlist


def augment_notesfile(fname, arch, optionlist):

    try:
        print(fname)
        with open(fname) as f:
            for line in f:

                elem = line.split()

                if len(elem) == 0:
                    continue

                if elem[0] != 'options' and elem[0] != '#options':
                    continue

                elemvalues = elem[1].split('=')

                if elemvalues[0] not in optionlist.keys():
                    optionlist[elemvalues[0]] = Option(elemvalues[0], arch)
                    print('New option not in options files ', elemvalues[0])

                optionlist[elemvalues[0]].innotes.add(
                    'global' if arch == Architecture.ALL else arch.value())
                optionlist[elemvalues[0]].default = elemvalues[1] if len(
                    elemvalues) > 1 else None

    except:
        return optionlist

    return optionlist


def special_options(option):
    if option in translatable_options.keys():
        return translatable_options[option]
    else:
        return []


def augment_mandir(args, optionlist):
    cmd = '/usr/bin/find /usr/share/man -exec grep -HZ \'.Cd "\?options\' {} \;'
    regex = re.compile('(?P<entry>.*)\\.(?P<section>[0-9]).gz')
    optentry = re.compile(
        '.*Cd "?options (?P<option>[a-zA-Z0-9_()|]+)(=(?P<default>[a-zA-Z0-9<>_]+))?"?')

    with Popen(cmd, stdout=PIPE, shell=True) as proc:
        for l in proc.stdout:
            manentry = regex.match(os.path.basename(str(l).split(':')[0]))
            record = '%s(%s)' % (manentry['entry'], manentry['section'])

            optionentry = optentry.match(str(l))

            if optionentry['option'] not in optionlist.keys():
                repl = special_options(optionentry['option'])

                if len(repl) == 0:
                    optionlist[optionentry['option']] = Option(
                        optionentry['option'],
                        Architecture.UNKNOWN)
                    optionlist[optionentry['option']].manentries.add(record)
                    if optionentry['default'] is not None:
                        optionlist[optionentry['option']
                                   ].default = optionentry['default']
                    continue
                for opt in repl:
                    if opt not in optionlist.keys():
                        print('New option from man entries ', opt)

                        optionlist[opt] = Option(opt, Architecture.UNKNOWN)
                        optionlist[opt].manentries.add(record)
                        if optionentry['default'] is not None:
                            optionlist[opt].default = optionentry['default']
            else:
                optionlist[optionentry['option']].manentries.add(record)
                if optionentry['default'] is not None:
                    optionlist[optionentry['option']
                               ].default = optionentry['default']


def get_src_revision(src):
    """"""

    revisionstr = b'REVISION='
    branchstr = b'BRANCH='

    with open(src+'/sys/conf/newvers.sh', 'rb', 0) as f, \
            mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as s:
        offset = s.find(revisionstr)

        if offset != -1:
            s.seek(offset+len(revisionstr))
            rev = s.readline().decode().replace('\n', '').replace('"', '')

        offset = s.find(branchstr)

        if offset != -1:
            s.seek(offset+len(branchstr))
            branch = s.readline().decode().replace('\n', '').replace('"', '')

        return rev, branch


def parse_options(args):

    optionlist = {}

    for src in args.src:

        rev, branch = get_src_revision(src)

        print('Processing %s-%s in source tree %s' % (rev, branch, src))

        for a in Architecture:
            if a == Architecture.UNKNOWN:
                continue

            fname = src+'/sys/conf/options'

            if a != Architecture.ALL:
                fname += '.%s' % (a.value.lower())

            optionlist = parse_file(fname, a, optionlist)

            optionlist = augment_notesfile(src+'/sys/conf/NOTES',
                                           Architecture.ALL, optionlist)

        for a in Architecture:
            if a == Architecture.ALL or a == Architecture.UNKNOWN:
                continue

            optionlist = augment_notesfile('%s/sys/%s/conf/NOTES' % (src, a.value.lower()),
                                           a,
                                           optionlist)

            augment_mandir(args, optionlist)

    return optionlist


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('src',
                        nargs='*',
                        default=['/usr/src'],
                        help='Path to top-level directory of the FreeBSD sources')
    parser.add_argument('--ver', default='11.2',
                        help='FreeBSD release')

    args = parser.parse_args()

    optionlist = parse_options(args)

    import pdb
    pdb.set_trace()

    for opt in sorted(optionlist):
        optionlist[opt].collapse()
        print('%s\t%s\t%s\t%s\t%s\t%s' % (opt, optionlist[opt].innotes,
                                          optionlist[opt].file,
                                          optionlist[opt].arch,
                                          optionlist[opt].default,
                                          optionlist[opt].manentries))
