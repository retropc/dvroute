# dvroute -- dynamic vpn router
#
# Copyright (C) 2013 Chris Porter
# Licensed under GPLv2 -- see LICENCE

# TODO: better logging
#       timeout/expiry based on ttl
#       getopt and fork instead of shell script

import re
import socket
import traceback
import subprocess
import sys
import os
import pwd
import grp
from twisted.internet import reactor
from twisted.names import dns, client, server
import config

NETFLIX_RE = re.compile(r"\A(.+\.)?(netflix\.com|netflix\.net|nflximg\.net)\.?\Z", re.IGNORECASE)
MARK = "2"
IPTABLES = "/sbin/iptables"
CHAIN = "dvroute"

class Resolver(client.Resolver):
  def __init__(self, fd, *args, **kwargs):
    kwargs["servers"] = config.LOCAL_DNS
    client.Resolver.__init__(self, *args, **kwargs)

    self.fd = fd
    self.added = set()
    self.cnames = set()

  def got_A(self, address, ttl):
    if address in self.added:
      return

    try:
      os.write(self.fd, normalise(address) + "\n")
      INFO("added %r" % address)
      self.added.add(address)
    except ValueError:
      WARN("Invalid IP: %r" % address)

  def got_CNAME(self, address, ttl):
    INFO("watching %r" % address)
    self.cnames.add(address)

  def queryUDP(self, queries, timeout=None):
    intercept = False
    self.servers = config.LOCAL_DNS
    if len(queries) > 0:
      n = str(queries[0].name)
      if NETFLIX_RE.match(n): # or n in self.cnames:
        self.servers = config.REMOTE_DNS
        INFO("querying remote server for %r" % n)
        intercept = True
      
    result = client.Resolver.queryUDP(self, queries, timeout)

    if intercept:
      def callback(answer):
        for a in answer.answers:
          if a.type == dns.A:
            self.got_A(socket.inet_ntoa(a.payload.address), a.payload.ttl)
          elif a.type == dns.CNAME:
            self.got_CNAME(str(a.payload.name), a.payload.ttl)
        return answer
      result = result.addCallback(callback)
    return result

def iptables_add(ip):
  return iptables_alter(ip, add=True)

def iptables_remove(ip):
  return iptables_alter(ip, add=False)

def iptables_alter(ip, add=True):
  try:
    ip = normalise(ip)
    iptables_exec(add and "-A" or "-D", CHAIN, "-d", ip, "-j", "MARK", "--set-mark", MARK)
  except ValueError: 
    WARN("Bad ip: %r" % ip)
  except subprocess.CalledProcessError, e:
    WARN("Unable to add to iptables", e)

def iptables_flush():
  iptables_exec("-F", CHAIN)

def iptables_exec(*args):
  subprocess.check_call([IPTABLES, "-t", "mangle"] + list(args), shell=False)

def WARN(x, e=None):
  print >>sys.stderr, "WARN", x
  if e:
    traceback.print_exc(e, sys.stderr)

def INFO(x, e=None):
  print >>sys.stderr, "INFO", x
  if e:
    traceback.print_exc(e, sys.stderr)

def normalise(ip):
  octets = ip.split(".")
  ip_normalised = []
  if len(octets) != 4:
    raise ValueError
  for x in octets:
    x = int(x)
    if x < 0 or x > 255:
      raise ValueError
    ip_normalised.append(str(x))
  return ".".join(ip_normalised)

def run_child(r):
  try:
    os.dup2(r, 0)

    while True:
      line = sys.stdin.readline()
      if not line:
        os._exit(0)
      iptables_add(line.strip())
  except:
    traceback.print_exc()
  finally:
    os._exit(1)

def drop_privs():
  gid = grp.getgrnam(config.GID).gr_gid
  uid = pwd.getpwnam(config.UID).pw_uid

  os.setgroups([])
  os.setgid(gid)
  os.setuid(uid)
  os.chdir("/")

def main():
  if os.getuid() != 0:
    raise Exception("Must run as root")

  iptables_flush()

  os.close(0)
  os.closerange(2 + 1, subprocess.MAXFD)

  r, w = os.pipe()
  pid = os.fork()
  if pid == 0:
    run_child(r)

  os.close(r)

  resolver = Resolver(w)
  factory = server.DNSServerFactory(clients=[resolver])
  protocol = dns.DNSDatagramProtocol(factory)

  reactor.listenUDP(53, protocol)
  reactor.listenTCP(53, factory)

  drop_privs()
  reactor.run()

if __name__ == "__main__":
  main()
