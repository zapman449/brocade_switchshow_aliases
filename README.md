brocade_switchshow_aliases
==========================

Pulls switchshow from a fabric of brocade Fiber Channel switches, and 
shows aliases with WWNs

Short version: switchshow is great, if you can memorize WorldWide Numbers.

I can't.  

So I wrote something to pull the zoneshow information, parse out the aliases
data, and where a wwn appears in switchshow, it will also display the alias
for the WWN if there is one.

Bonus: This understands how to get WWPN's from L-Port, and from NPIV F-Port
ports.

Assumptions:
1) A single host can access SSH for all of your switches in a fabric.
2) All switches in a fabric have the same username/password pair with the
rights to run 'switchshow', 'zoneshow', and 'portshow'.  You'll be prompted
for that username/password at runtime.

Outputs:
This will create a zoneshow.{fabricname} file, which has the zoneshow data.

This will create a aliases.{fabricname} file, which has a cleaned up alias
data for the fabric (pulled from zoneshow).

This will create a switchshow.{switchname} file for each switch in a fabric
which has the cleaned up switchshow output, augmented with the alias data, and
with NPIV and L-Port data exposed.

Steps to get it working:
1) Modify the config file: get_brocade.conf

This config files defines which switches are in which fabrics.  The file has
lines in the form {switch_host_name} => {fabric_name}.  Specify as many
switches and fabrics as you want.  Each run of the command can analyze one
fabric's switches.

2) run 'get_brocade.py {fabric_name}'

3) read output.
