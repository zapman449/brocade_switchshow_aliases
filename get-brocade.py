#!/usr/bin/python

"""
Reach out to a set of brocade SAN switches. Save copies of switchshow and
zoneshow (only once per fabric).  Enhance switchshow output by finding 
aliases for various WWNs.  Understand NPIV, looking up WWNs from L-Ports, etc.
Should work on all recent switches 4100 or higher.  May work older.  Should
work on DCX class switches as well, though I can't test that.
"""

import getpass
import os.path
import paramiko
import sys

# NOTE 1: This script assumes that for a given fabric, the admin 
# username/passwords are the same. 
# NOTE 2: if you use FQDN's below, and they DON'T end in '.com', '.net', or
# '.org', you'll need to tweak an if clause in 'main'.  Should be obvious.

CONFIG = 'get-brocade.conf'

pw = ''         # Prompt for these later.
user = ''       # Prompt for these later.
aliasdb = {}

def alias_split(cache) :
    """helper function. splits the unified alias lines. adds data to aliasdb"""
    del(cache[0]) # delete 'alias:'
    name = cache[0]
    del(cache[0]) # delete 'name'
    for wwn in cache :
        f = wwn.replace(';', '')
        aliasdb[f] = name

def connect(switch) :
    """actually connects to a switch.  returns a paramiko connection"""
    global user
    global pw
    conn = paramiko.SSHClient()
    conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    conn.connect(switch, username=user, password=pw)
    return conn

def run_cmd(conn, command) :
    """runs a given command against a switch connection"""
    stdin, stdout, stderr = conn.exec_command(command)
    stdin.close()
    return stdout.readlines()

def get_zoneshow(conn, fabric) :
    """Runs zoneshow on the first switch in a fabric, and parses the results
    Used to split out the 'aliases' block.  
    Also save a copy locally for study"""
    zoneshow = run_cmd(conn, 'zoneshow')
    zonefile = open('zoneshow.%s' % fabric, 'w')
    aliasfile = open('aliases.%s' % fabric, 'w')
    SKIPPING = True
    cache = []
    for line in zoneshow :
        zonefile.write(line)
        uline = line.strip()
        words = uline.split()
        if SKIPPING :
            if words[0] == 'alias:' :
                SKIPPING = False
                # intentionally falling through to the next IF clause
            else :
                continue
        if not SKIPPING :
            if len(words) == 0 :
                # a blank line finishes the aliases
                aliasfile.write(' '.join(cache) + '\n')
                alias_split(cache)
                return 0
            elif words[0] == 'alias:' :
                if cache != [] :
                    aliasfile.write(' '.join(cache) + '\n')
                    alias_split(cache)
                    cache = []
                cache.extend(words)
            elif line.startswith("   ") or line.startswith("	") :
                cache.extend(words)
            else :
                print 'should not be here... ', uline

def get_portshow(conn, port) :
    """given a connection and a port#, return a list of WWN's connected to it"""
    portshow = run_cmd(conn, 'portshow %s' % port)
    SKIPPING = True
    results = []
    counter = 0
    for line in portshow :
        counter += 1
        if SKIPPING :
            if line.startswith('portWwn of device') :
                SKIPPING = False
        else :
            if line.startswith('Distance') :
                break
            uline = line.strip()
            words = uline.split()
            results.append(words[0])
    return results

def parse_switch_line(conn, header, line) :
    """the meat of the program.  Parses one port state line from switchshow"""
    uline = line.strip()
    words = uline.split()
    del words[0]        # delete the 'Area' or 'Index' which is useless.
    if 'Slot' in header :
        # make a DCX or otherwise bladed FC switch work like a non bladed
        newport = '/'.join(words[0:2])
        del(words[0])
        words[0] = newport
    if 'Address' in header :
        del(words[1])
    del(words[1])   # delete the 'id' column
    if ' FC' in uline :
        del(words[3])
    # so. at this point, words should contain port#, speed, state, porttype
    # type and what I'll term 'message'.
    if 'Disabled' in line :
        return [words[0], words[1], 'Disabled']
    if 'No_Card' in line :
        return [words[0], words[1], 'No_Card']
    if 'Laser_Flt' in line :
        return [words[0], words[1], 'Laser_Fault']
    if 'Diag_Flt' in line :
        return [words[0], words[1], 'Port_Diag_Fault']
    if 'Lock_ref' in line :
        return [words[0], words[1], 'Locking_Reference']
    if 'Testing' in line :
        return [words[0], words[1], 'Testing']
    if words[2] == 'No_Light' or 'Sync' in words[1] :
        return words
    if len(words) == 3 :
        return words
    portnum, speed, state, porttype = words[:4]
    message = " ".join(words[4:])
    if words[2] == 'No_Module' :
        del(words[4:])
        words.append(message)
        return words
    if porttype == 'E-Port' :
        del(words[4:])
        words.append(message)
        return words
    if porttype == 'L-Port' or 'NPIV' in message :
        # message is useless, must get portshow.
        wwns = get_portshow(conn, portnum)
        data = []
        for wwn in wwns :
            if wwn in aliasdb :
                data.append((wwn, aliasdb[wwn]))
            else :
                data.append((wwn, 'no_alias'))
        newmessage = ' | '.join(map(' => '.join, data))
        del(words[4:])
        words.append(newmessage)
        return words
    if porttype == 'F-Port' :
        wwn = message
        alias = 'no_alias'
        if wwn in aliasdb :
            alias = aliasdb[wwn]
        newmessage = ' => '.join((wwn, alias))
        del(words[4:])
        words.append(newmessage)
        return words

def get_switchshow(conn, switch) :
    """Runs switchshow, and parses output (with parse_switch_line's help).
    Writes modified switchshow output to switchshow.<switchname>"""
    ss_name = 'switchshow.%s' % switch
    outfile = open(ss_name, 'w')
    switchshow = run_cmd(conn, 'switchshow')
    SKIPPING = True
    header = ''
    outfile.write('Port Speed State    PortType  [WWN => alias] ...\n')
    outfile.write('================================================\n')
    for line in switchshow :
        uline = line.strip()
        if SKIPPING :
            #outfile.write(line)
            if 'Speed' in uline :
                header = uline
            if line.startswith('=============') :
                SKIPPING = False
        else :
            # start parsing the ports
            words = parse_switch_line(conn, header, line)
            #outfile.write('  '.join(words) + '\n')
            #outfile.write("%2s %s %9s %s %s\n" % words)
            #print repr(words)
            if len(words) == 3 :
                outfile.write("%2s   %s    %-9s\n" % (words[0], words[1],
                                                   words[2]))
            else  :
                outfile.write("%2s   %s    %-9s %s   %s\n" % (words[0],
                                        words[1], words[2], words[3], words[4]))

def USAGE() :
    """print usage message"""
    print "USAGE: %s <fabric_name>" % sys.argv[0]
    print "where <fabric_name> is defined in the config file: %s" % CONFIG
    print 'exiting'

def parse_config() :
    global CONFIG
    conf = open(CONFIG, 'r')
    switches = {}
    for line in conf :
        if line.startswith('#') :
            continue
        if line.startswith(" ") :
            continue
        if len(line) <= 4 :
            continue
        words = line.strip().split()
        if len(words) != 3 and words[1] != '=>' :
            print 'failure to parse config file line.  line is:'
            print line.strip()
            print 'exiting'
            sys.exit()
        switch = words[0]
        fabric = words[2]
        switches.setdefault(fabric, []).append(switch)
    return switches

def main() :
    global user
    global pw
    global CONFIG
    if not os.path.isfile(CONFIG) :
        USAGE()
        sys.exit()
    switches = parse_config()
    # Parse the commandline args.
    if len(sys.argv) != 2 :
        USAGE()
        sys.exit()
    if sys.argv[1] not in switches :
        print 'fabric name not found in config file: %s' % CONFIG
        sys.exit()
    fabric = sys.argv[1]
    user = raw_input("Switch Username: ")
    pw = getpass.getpass('Switch password for user %s: ' % user)
    first = True
    for switch in switches[fabric] :
        conn = connect(switch)
        if first :
            get_zoneshow(conn, fabric)
            first = False
        # this is a somewhat naive test for if a switch name is an FQDN, but...
        if switch.endswith('.com') or switch.endswith('.net') or \
                                      switch.endswith('.org') :
            switch = switch[0:switch.find('.')]
        get_switchshow(conn, switch)
    conn.close()

if __name__ == '__main__' :
    main()
