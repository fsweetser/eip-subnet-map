#!/usr/bin/python

from SOLIDserverRest import *
from SOLIDserverRest import adv as sdsadv
import getpass
import logging
import csv
import time
import json
import pprint
import ipaddress
import argparse

# Subnet mask and prefix are both missing from the REST API output, so
# this helper function calculates the prefix from the start and end
# properties.  Note that it assumes that the start and end are
# properly aligned on subnet bit boundaries.

def range_to_mask(subnet):
    lower = int(subnet['start_ip_addr'], 16)
    upper = int(subnet['end_ip_addr'], 16)

    mask = upper - lower

    return(32 - bin(mask).count("1"))

args = argparse.ArgumentParser()
args.add_argument("-s", "--server", help="Hostname or IP of EIP database server", required=True)
args.add_argument("-u", "--username", help="Username to authenticate to EIP with", required=True)
args.add_argument("-b", "--block", help="Starting IP address of the block to use as the root", required=True)
args.add_argument("-l", "--lowerbound", help="CIDR mask of the smallest subnets to display (default 24)", type=int, default=24)

args = args.parse_args()

base = args.block
lowerbound = args.lowerbound

subnets = {}
blocks = {}

SDS_PWD = getpass.getpass()

sds = sdsadv.SDS(ip_address = args.server,
                 user       = args.username,
                 pwd        = SDS_PWD)


try:
    sds.connect()
except SDSError as e:
    logging.error(e)
    exit(1)

# Pull down the block we're interested in.  Note that it must be a
# non-terminal container block (if it is a terminal subnet, there's
# nothing under it, so why are you even looking?)

params = {
    "WHERE":   f"start_hostaddr='{base}' and is_terminal='0'",
    "ORDERBY": "subnet_level asc",
    "limit":   1
    }

try:
    parent = sds.query(method="ip_subnet_list", params = params, timeout = 5)
except SDSEmptyError as e:
    logging.error(e)
    logging.error("Block parameter must point at the starting IP address of an existing non-terminal block")
    exit()
        
parent = parent[0]

basemask = range_to_mask(parent)

parentnet = ipaddress.ip_network(parent['start_hostaddr'] + '/' + str(basemask))

# Pre-populate the subnet structure with all possible subnets as "free". Go
# all the way to /31 to allow for hidden subnets below the lower bound so as
# to make unavailable/free status accurate.

for mask in range(basemask, 31):
    subnets[mask] = {}
    children = list(parentnet.subnets(new_prefix=mask))
    for child in children:
        subnets[mask][int(child.network_address)] = {
            "name": "Free",
            "status": "free",
            "network": str(child)
            }

# Stuff the parent block in, since it won't get enumerated while going
# through all child subnets.

blocks[basemask] = {}
blocks[basemask][int(parentnet.network_address)] = {
    "name": parent['subnet_name'],
    "network": parent['start_hostaddr'] + "/" + str(basemask)
    }

# No idea what the subnets of size zero are doing in the results, but
# make sure to filter them out.

params = {
    "WHERE": f"parent_subnet_path like '{parent['subnet_path']}%' and subnet_size > 0",
    "ORDERBY": "start_ip_addr"
    }

children = sds.query(method="ip_subnet_list", params = params, timeout = 5)

# Stuff the results of all subnets and blocks underneath the parent
# block into their respective data structures.

for child in children:
    mask = range_to_mask(child)

    # Process the subnets
    if child['is_terminal'] == "1":
        if mask not in subnets:
            subnets[mask] = {}

        intaddr = int(child['start_ip_addr'], 16)

        # Since we're pulling data straight from IPAM, we assume that
        # it's valid and there are no overlapping subnets.
        
        # Mark the subnet itself as used
        subnets[mask][intaddr] = {
            "name": child['subnet_name'],
            "network": child['start_hostaddr'] + '/' + str(mask),
            "status": "used"
            }

        # Mark all parent subnets as unavailable
        for i in range(basemask, mask):
            chaddr = ipaddress.ip_network(child['start_hostaddr'] + '/' + str(mask))
            intaddr = int(chaddr.supernet(new_prefix=i).network_address)
            subnets[i][intaddr]['name'] = "Unavailable"
            subnets[i][intaddr]['status'] = "notfree"

        # Mark all child subnets as unavailable
        chaddr = ipaddress.ip_network(child['start_hostaddr'] + '/' + str(mask))
        for i in range(mask+1, lowerbound+1):
            subs = list(chaddr.subnets(new_prefix=i))
            for sub in subs:
                intaddr = int(sub.network_address)
                subnets[i][intaddr]['name'] = "Unavailable"
                subnets[i][intaddr]['status'] = "notfree"

    # Process the blocks.  We don't go up and down the levels for
    # blocks, as they can overlap without conflict.  We also don't
    # worry about populating levels that contain no blocks, as
    # that wouldn't tell us anything useful.
    else:
        if mask not in blocks:
            blocks[mask] = {}
            supernet = ipaddress.ip_network(parent['start_hostaddr'] + '/' + str(basemask))
            peers = list(supernet.subnets(new_prefix=mask))
            for peer in peers:
                blocks[mask][int(peer.network_address)] = {
                    "name": "Free",
                    "status": "free",
                    "network": str(peer)
                    }

        blocks[mask][int(child['start_ip_addr'], 16)] = {
            "name": child['subnet_name'],
            "network": child['start_hostaddr'] + "/" + str(mask)
            }

# Dump it all out into a grid.  Fun fact: tables don't work reliably
# here, as browsers see a TD with colspan of 8192 as an "obviously
# wrong" value and cap colspan at around 2k, making the resulting
# table wrong.  Grids do not appear to have this arbitrary limitation.
print(f"""<!DOCTYPE html>
<html>
<head>
<title>Suballocations for {parent['subnet_name']}</title>

<style>
.grid-table {{
  display: grid;
}}

.table-free {{
 border: 2px solid black;
 box-sizing: border-box;
 padding: 2px;
 background-color: #D1FFBD;
 text-align: center;
}}

.table-used {{
 border: 2px solid black;
 box-sizing: border-box;
 padding: 2px;
 background-color: #D5FFFF;
 text-align: center;
}}

.table-notfree {{
 border: 2px solid black;
 box-sizing: border-box;
 padding: 2px;
 background-color: #FFE6E6;
 text-align: center;
}}

.table-block {{
 border: 2px solid black;
 box-sizing: border-box;
 padding: 2px;
 background-color: #BDBDBD;
 text-align: center;
}}
</style>

</head><body>""")

print("<div class=\"grid-table\">")

for level in range(basemask, lowerbound+1):

    colwidth = 2 ** (lowerbound - level)
    
    if level in blocks:
        for eachblock in sorted(blocks[level]):
            tclass = "table-block"
            label = blocks[level][eachblock]['name'] + "<br/>" + blocks[level][eachblock]['network'] + "<br/>block"
            print("<div class=\"", tclass, "\" style=\"grid-column: span ", colwidth, ";\">", label, "</div>", sep="")


    for eachsub in sorted(subnets[level]):
        label = subnets[level][eachsub]['name'] + "<br/>" + subnets[level][eachsub]['network'] + "<br/>" + subnets[level][eachsub]['status']
        tclass = "table-" + subnets[level][eachsub]['status']
        print("<div class=\"", tclass, "\" style=\"grid-column: span ", colwidth, ";\">", label, "</div>", sep="")

print("</div>")
print("</body></html>")

