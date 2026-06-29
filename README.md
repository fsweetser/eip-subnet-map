# eip-subnet-map
Create a useful view of subnet usage from Efficient IP IPAM data.  Call it with block you are interested in, and it
will produce and generate an HTML table of subnet utilization on stdout.

Please note that the block argument must point at a non-terminal subnet object that already exists in IPAM.

```
usage: eip-subnet-map.py [-h] -s SERVER -u USERNAME -b BLOCK [-l LOWERBOUND]

optional arguments:
  -h, --help            show this help message and exit
  -s SERVER, --server SERVER
                        Hostname or IP of EIP database server
  -u USERNAME, --username USERNAME
                        Username to authenticate to EIP with
  -b BLOCK, --block BLOCK
                        Starting IP address of the block to use as the root
  -l LOWERBOUND, --lowerbound LOWERBOUND
                        CIDR mask of the smallest subnets to display (default 24)
```
