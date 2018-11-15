#!/usr/bin/python3

import git
import json
import os
import re
import resource
import shutil as sh
import stat
import subprocess as sp
import zipfile as zf

class pushd:
    currd = None
    prevd = None
    def __init__(self, dirname):
        self.currd = os.path.abspath(dirname)
    def __enter__(self):
        self.prevd = os.getcwd()
        os.chdir(self.currd)
        return self
    def __exit__(self, type, value, traceback):
        os.chdir(self.prevd)

def title(str):
    print('\033]0;' + str, end='\007\n')

def need(prg):
    if not (os.path.exists(prg) and os.access(prg, os.X_OK)):
        raise Exception('File ' + prg + ' does not exist or is not executable.')

MAX_VIRTUAL_MEMORY = 2 * 1024 * 1024 * 1024 # 2GB
NORMAL_TIMEOUT = 30
SLOW_TIMEOUT = 4 * NORMAL_TIMEOUT
KILL_TIMEOUT = 5

def limit_memory():
    resource.setrlimit(resource.RLIMIT_AS, (MAX_VIRTUAL_MEMORY, resource.RLIM_INFINITY))

def make(target):
    title('Making %s' %(target))
    sp.call(['/usr/bin/python2',
            'tools/configure.py',
            '--output-directory', './src',
            '--source-directory', 'src-input',
            '--config-metadata', 'config',
            '--option-file', 'util/makeduk_base.yaml',
            '--line-directives'])
    sp.call(['make', '-f', 'dist-files/Makefile.cmdline'])
    sh.move('duk', target)

def tests(dirname):
    global jsregex;
    for test in os.listdir(dirname):
        testname = os.path.join(dirname, test)
        if os.path.isfile(testname) and jsregex.match(test):
            yield testname
        elif os.path.isdir(testname):
            for subtest in tests(testname):
                yield subtest

def run(duk):
    expectregex = re.compile(r'^/\*===\n(.*?)===\*/\n', re.MULTILINE | re.DOTALL)
    paramsregex = re.compile(r'^/\*---\n(.*?)---\*/\n', re.MULTILINE | re.DOTALL)
    pex_skip    = re.compile(r'"skip"\s*:\s*true')
    pex_slow    = re.compile(r'"slow"\s*:\s*true')
    S_tout = 0
    S_skip = 0
    EtM='../elf-to-map.py'
    CtG='../chain-to-graph.py'
    CGF='../convert-graph-formats.py'
    need(EtM)
    need(CtG)
    need(CGF)
    need(duk)
    if os.path.exists('tracer.chains'):
        os.remove('tracer.chains')
    dukname = os.path.basename(duk)
    idx = 0
    with open(dukname + '-passfail.data', 'w') as pfdata:
        for test in tests('tests'):
            idx += 1
            title('Testing %s with TC%d (%s)' % (duk, idx, test))
            expected = ''
            params = ''
            try:
                with open(test, "rt") as testfile:
                    data = testfile.read()
                    for part in expectregex.findall(data):
                        expected += part
                    for part in paramsregex.findall(data):
                        params += part
            except Exception as e:
                print(str(e))
                continue
            if pex_skip.search(params):
                print("Skipping %s" % (test))
                idx -= 1
                S_skip += 1
                continue
            proc = sp.Popen([duk, test], stdout=sp.PIPE, stderr=sp.PIPE, encoding='utf8', preexec_fn=limit_memory)
            try:
                result = proc.communicate(timeout=(SLOW_TIMEOUT if pex_slow.search(params) else NORMAL_TIMEOUT))[0]
            except sp.TimeoutExpired:
                proc.terminate()
                proc.communicate(timeout=KILL_TIMEOUT)
                if proc.poll() == None:
                    proc.kill()
                    proc.communicate()
                    print("Timeout, KILL TC%d: %s" % (idx, test))
                else:
                    print("Timeout, TERM TC%d: %s" % (idx, test))
                result = None
                S_tout += 1
            pfdata.write(str(idx) + (':PASS:' if result == expected else ':FAIL:') + test + '\n')
    print("%d tests were skipped\n%d tests are timeouted" % (S_skip, S_tout))
    title('Processing chains')
    sh.move('tracer.chains', dukname + '.chains')
    sp.call([CtG, '-m', '-g', dukname + '.chains'])
    sp.call([EtM, duk, dukname + '.dynamic.map'])
    sp.call([CGF, dukname + '.chains.all.graph.json', dukname + '.dynamic.graphml', '-m',  dukname + '.dynamic.map'])
    sp.call(['gzip', dukname + '.chains'])
    sp.call(['gzip', dukname + '.chains.all.graph.json'])
    sp.call(['gzip', dukname + '.dynamic.graphml'])

jsregex = re.compile(r'^(.*)\.js$')

try:
    make('duk-traced')
    run('./duk-traced')
except Exception as e:
    print(str(e))
else:
    pass
finally:
    pass
title('Done')
