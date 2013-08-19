Dynamic VPN Router
==================

I wrote this program to allow me to watch US Netflix on my Smart TV in the UK, while still allowing operation of apps like BBC iPlayer (UK).

It runs a small DNS server which looks at DNS queries and inserts iptables rules to re-route the traffic as required.

### Routing example

+ www.example.com -> not interesting -> send to normal DNS server and do not add routing rules
+ www.netflix.com -> interesting -> send to VPS DNS server, then route all traffic to the resolved address over the VPN.

### Notes

Setup is reasonably complicated, requiring a Linux machine on your LAN, and a remote VPS with an IP address that the service you're interested in allows you to use.

A VPN is created between the machines (with OpenVPN), then dvroute runs on the home Linux machine.

The TV then has its default gateway and DNS server set to your LAN Linux machine, which performs the routing decisions.

Example configuration
=====================

Things you will likely need to change are in **bold**!

The following example values are provided to give some idea of how it all hangs together:

    Home LAN subnet    : 192.168.1.0/24 (trusted)
    Home LAN Linux IP  : 192.168.1.10
    Home LAN TV IP     : 192.168.1.30
    Home public IP     : 172.16.44.11 (assumed static)

    VPS hostname       : vps.tv.example.com
    VPS IP             : 169.254.13.22

VPS and Home LAN Linux machine are both Debian 7.0.
Home LAN is assumed to be trusted, VPS network is assumed to be untrusted.

If you have a dynamic IP you can either not add the OpenVPN IP allowing rules, or come up with some other solution.

TV setup
--------

<pre>
IP          : <b>192.168.1.30</b>
Subnet mask : <b>255.255.255.0</b>
Gateway     : <b>192.168.1.10</b>
DNS         : <b>192.168.1.10</b>
</pre>

Home LAN Linux machine setup
----------------------------

(as root)

In dvroute directory: <pre>cp config.py.example config.py</pre>

Edit config.py to make neccessary changes for your setup.

    echo "/path/to/dvroute/dvroute || echo" > /etc/rc.local
    apt-get install openvpn python-twisted-names
    openvpn --genkey --secret /etc/openvpn/vps.key
    echo "201  vps" > /etc/iproute2/rt_tables

Create config files:

###### /etc/openvpn/vpn.conf

<pre>
remote <b>vps.tv.example.com</b>
dev tun
ifconfig 10.8.0.2 10.8.0.1
secret vps.key
up /etc/openvpn/vps-up.sh
script-security 2
</pre>

###### /etc/openvpn/vps-up.sh

    #!/bin/sh
    /sbin/ip route add default via 10.8.0.2 dev tun0 table vps
    /sbin/ip route flush cache

###### /etc/network/if-pre-up.d/firewall

    #!/bin/sh
    /sbin/ip rule ls | /bin/grep  "from all fwmark 0x2 lookup vps" >/dev/null || /sbin/ip rule add fwmark 2 table vps # HACK
    /sbin/iptables-restore < /etc/firewall.conf
    /sbin/sysctl -w net.ipv4.ip_forward=1

###### /etc/firewall.conf

<pre>
*filter
:INPUT ACCEPT [0:0]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -m mark --mark 0x2 -j SNAT --to-source 10.8.0.2
COMMIT
*mangle
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
:dvroute - [0:0]
## any rules you want to selectively route on go here, for example my TV is 192.168.1.30, so I have:
-A PREROUTING -s <b>192.168.1.30/32</b> -j dvroute
## to send all traffic instead:
## -A PREROUTING -j dvroute
COMMIT
</pre>

Set permissions:

    chmod 600 /etc/firewall.conf /etc/openvpn/vps.key
    chmod 700 /etc/openvpn/vps-up.sh /etc/network/if-pre-up.d/firewall

VPS machine setup
-----------------

(as root)

Install OpenVPN and dnsmasq:

    apt-get install openvpn dnsmasq

Copy /etc/openvpn/vps.key from your Home LAN Linux machine to this machine exactly.

Create config files:

###### /etc/openvpn/vps.conf

    dev tun
    ifconfig 10.8.0.1 10.8.0.2
    secret vps.key

###### /etc/network/if-pre-up.d/firewall

    #!/bin/sh
    /sbin/iptables-restore < /etc/firewall.conf
    /sbin/sysctl -w net.ipv4.ip_forward=1

###### /etc/firewall.conf
<pre>
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
# you probably want to allow ssh in still
-A INPUT -p tcp -m tcp --dport 22 -j ACCEPT
-A INPUT -i tun0 -p tcp -m tcp --dport 53 -j ACCEPT
-A INPUT -i tun0 -p udp -m udp --dport 53 -j ACCEPT
# Home public IP address
-A INPUT -s <b>172.16.44.11</b> -p udp -m udp --dport 1194 -j ACCEPT
-A INPUT -p icmp -j ACCEPT
-A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A FORWARD -i tun0 -o eth0 -j ACCEPT
COMMIT
*nat
:PREROUTING ACCEPT [0:0]
:INPUT ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
:POSTROUTING ACCEPT [0:0]
# vps IP address
-A POSTROUTING -s 10.8.0.2/32 -o eth0 -j SNAT --to-source <b>169.254.13.22</b>
COMMIT
</pre>

Set permissions:

    chmod 600 /etc/firewall.conf /etc/openvpn/vps.key
    chmod 700 /etc/network/if-pre-up.d/firewall

Final steps
-----------

* For simplicity reboot both the Home LAN Linux machine and the VPS (otherwise restart the stacks yourself, and start the openvpns).
* Try watching TV!

Diagnostics
-----------

### Home LAN Linux machine

#### Tunnel up?
    ping 10.8.0.1

#### TV sending traffic to the gateway (while pinging)?
<pre>tcpdump -i eth0 host <b>192.168.1.30</b></pre>

#### Traffic traversing the tunnel (while pinging)?
    tcpdump -i tun0

#### Does the routing table mark rule exists and the priorities correct?
    ip rule ls

#### Is the routing table correct?
    ip route ls table vps

#### Is iptables correctly configured?
    iptables -t -L
    iptables -t nat -L
    iptables -t mangle -L

#### Does dvroute run?
(make sure not already running first!)

    sudo dvroute -n

#### Does remote DNS work?
    dig www.netflix.com @10.8.0.1
    
#### Is dvroute running/working?
    dig www.netflix.com @127.0.0.1
    dig www.example.com @127.0.0.1

### VPS

#### Tunnel up?
    ping 10.8.0.2

#### Is LAN OpenVPN sending traffic to the VPS (while pinging)?
<pre>tcpdump -i eth0 host <b>172.16.44.11</b></pre>

#### Traffic traversing the tunnel (while pinging)?
    tcpdump -i tun0

#### Is iptables correctly configured?
    iptables -t -L
    iptables -t nat -L

#### Does dnsmasq work?
    dig www.example.com @127.0.0.1
