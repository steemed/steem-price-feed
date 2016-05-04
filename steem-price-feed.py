#! /usr/bin/env python

import os
import sys
import time
import math
import json
import random
import signal
import datetime

import dateutil.parser

import requests
import yaml

SQRT2 = math.sqrt(2.0)

SEC_PER_HR = 3600.0       # 3600 seconds/hr
MAX_HIST = 1000           # 1000 tx
SLEEP_GRANULARITY = 0.25  # 0.25 sec
LOOP_GRANULARITY = 0.25   # 1/4 of the min_publish_interval

class DebugException(Exception):
  pass

class GracefulKiller:
  # https://stackoverflow.com/a/31464349
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True


class WalletRPC(object):
  def __init__(self, ip, port, rpcuser, rpcpassword):
    self.url = "http://%s:%s/rpc" % (ip, port)
    self.rpcuser = rpcuser
    self.rpcpassword = rpcpassword
    self._headers = {'content-type': 'application/json'}
    self._jsonrpc = "1.0"
    self._id = 1
    self._auth = (rpcuser, rpcpassword)
  def __call__(self, method, params=None):
    if params is None:
      params = []
    else:
      params = list(params)
    payload = {
      "method": method,
      "params": params,
      "jsonrpc": self._jsonrpc,
      "id": self._id
    }
    data = json.dumps(payload)
    response = requests.post(self.url, data=data,
                             headers=self._headers, auth=self._auth)
    return response.json()
  def is_locked(self):
    return self("is_locked")
  def unlock(self, password):
    if self.is_locked():
      return self("unlock", [password])
    return True


def random_number():
  try:
    random.seed(str(os.urandom(8)))
  except NotImplementedError:
    pass
  return random.random()


def timestamp(dt):
  delta = dt - datetime.datetime(1970, 1, 1)
  return delta.total_seconds()

def mean_stdev(a):
  n = len(a)
  a = [float(i) for i in a]
  mean = sum(a) / n
  squares = [(i - mean)**2 for i in a]
  return (mean, math.sqrt((1.0 / n) * sum(squares)))

def phi(x, mean, sigma):
  z = abs(x - mean) / float(sigma)
  return (1.0 + math.erf(z / SQRT2)) / 2.0

def usage(message=None):
  if message is not None:
    print "##"
    print "## ERROR: %s" % message
    print "##"
    print
  
  print "usage: %s config.yml" % os.path.basename(sys.argv[0])
  raise SystemExit


def load_config(config_name):
  with open(config_name) as f:
    s = f.read()
    try:
      config = yaml.safe_load(s)
    except Exception, e:
      usage(str(e))
  return config


def access(r, accessor):
  for i in accessor:
    try:
      r = r[i]
    except:
      raise TypeError("Can not access attribute '%s'." % (i,))
  return r


def get_exchange_data(specs, logfile, debug):
  if debug:
    logfile.write("## get_exchange_data\n")
    logfile.write(str(specs) + "\n")
  r = requests.get(specs['url'], data=specs['query_params'])
  j = r.json()
  if debug:
    logfile.write(str(j) + "\n")
  v = access(j, specs['accessor'])
  return v


def get_vw_price(market, logfile, debug):
  if debug:
    CatchallException = DebugException
    logfile.write("## get_vw_price\n")
  else:
    CatchallException = Exception
  price_volume = []
  total_volume = []
  for exchange_name in market:
    exch = market[exchange_name]
    try:
      price = get_exchange_data(exch['price'], logfile, debug)
      price = float(price)
      volume = get_exchange_data(exch['volume'], logfile, debug)
      volume = float(volume)
      price_volume.append(price * volume)
      total_volume.append(volume)
    except CatchallException, e:
      pass
  pv = sum(price_volume)
  v = float(sum(total_volume))
  if v <= 0:
    return 0
  return pv / v


def get_stm_usd_wvp(market_data, logfile, debug):
  btc_usd_wvp = get_vw_price(market_data['btc_usd'], logfile, debug)
  stm_btc_wvp = get_vw_price(market_data['steem_btc'], logfile, debug)
  return btc_usd_wvp * stm_btc_wvp


def get_previous_feed(wallet, witness):
  feed_time = None
  feed_price = None
  prev = wallet("get_account_history", [witness, -1, MAX_HIST])
  for n, t in prev['result']:
    if t['op'][0] == "feed_publish":
      feed_time = timestamp(dateutil.parser.parse(t['timestamp']))
      exch = t['op'][1]['exchange_rate']
      q = float(exch['quote'].split()[0])
      b = float(exch['base'].split()[0])
      feed_price = b / q
  return {"base": feed_price, "time": feed_time}

def get_price_history(wallet):
  feed_history = wallet("get_feed_history")
  price_history = feed_history['result']['price_history']
  history = []
  for pair in price_history:
    qp, qc = pair['quote'].split()
    bp, bc = pair['base'].split()
    if (qc == "STEEM") and (bc == "SBD"):
      history.append(float(bp) / float(qp))
  return history

def feed_loop(settings, market_data, wallet):
  killer = GracefulKiller()
  debug = settings.get("debug", False)
  is_live = settings.get("is_live", True)
  witness_name = settings['witness_name']
  min_pub_intrvl = settings['min_publish_interval'] * SEC_PER_HR
  max_pub_intrvl = settings['max_publish_interval'] * SEC_PER_HR
  min_change = settings['min_publish_change']
  logfile_name = settings.get("log_file", None)

  try:
    base = float(settings['default_base'])
  except:
    # if all else fails, default to current median history
    feed = wallet("get_feed_history")
    base = float(feed['current_median_history']['base'].split()[0])

  while True:
    if logfile_name is None:
      logfile = sys.stdout
    else:
      logfile = open(logfile_name, "a")
    loop_time = time.time()
    logfile.write("\n\nLoop at %s.\n" % time.ctime(loop_time))
    stm_usd_wvp = None
    do_update = False
    prev = get_previous_feed(wallet, witness_name)
    if debug:
      logfile.write(str(prev) + "\n")
    if prev['time'] == None:
      if debug:
        logfile.write("Time is None, updating.\n")
      do_update = True
    elif prev['time'] <= (loop_time - max_pub_intrvl):
      base = prev['base']
      if debug:
        logfile.write("Max time has expired, updating.\n")
      do_update = True
    elif prev['time'] > (loop_time - min_pub_intrvl):
      if debug:
        logfile.write("Min time has not elapsed, skipping.\n")
      do_update = False
    else:
      base = prev['base']
      stm_usd_wvp = get_stm_usd_wvp(market_data, logfile, debug)
      fraction = abs(base - stm_usd_wvp) / base
      if fraction >= min_change:
        if debug:
          logfile.write("%s >= %s, updating.\n" % (fraction, min_change))
        do_update = True
      else:
        if debug:
          logfile.write("%s < %s, skipping.\n" % (fraction, min_change))
        do_update = False
    if do_update:
      if stm_usd_wvp == None:
        stm_usd_wvp = get_stm_usd_wvp(market_data, logfile, debug)
      if stm_usd_wvp > 0:
        base = stm_usd_wvp
      history = get_price_history(wallet)
      mean, stdev = mean_stdev(history)
      p = phi(base, mean, stdev)
      r = random_number()
      logfile.write("Mean: %s | STDev: %s | p: %s | rand: %s\n" % (mean, stdev, p, r))
      if r < p:
        feed_base = "%0.3f SBD" % base
        feed_quote = "1.000 STEEM"
        exch_rate = {"base": feed_base, "quote": feed_quote}
        logfile.write(str(("publish_feed", [witness_name, exch_rate, True])) + "\n")
        if is_live:
          wallet("publish_feed", [witness_name, exch_rate, True])
    else:
      logfile.write("Skipping this round (%s).\n" % time.ctime(loop_time))
    if logfile_name is not None:
      logfile.close()
    sys.stderr.flush()
    sys.stdout.flush()
    while (time.time() - loop_time) < (min_pub_intrvl * LOOP_GRANULARITY):
      if killer.kill_now:
        logfile = open(logfile_name, "a")
        logfile.write("Caught kill signal, exiting.\n")
        logfile.close()
        break
      time.sleep(SLEEP_GRANULARITY)
    if killer.kill_now:
      break

def main():
  if len(sys.argv) != 2:
    usage()
  config_name = sys.argv[1]
  if not os.path.exists(config_name):
    usage('Config file "%s" does not exist.' % config_name)
  if not os.path.isfile(config_name):
    usage('"%s" is not a file.' % config_name)
  config = load_config(config_name)

  settings = config['settings']
  market_data = config['market_data']

  wallet = WalletRPC(settings['rpc_ip'], settings['rpc_port'],
                     settings['rpc_user'], settings['rpc_password'])

  if not wallet.unlock(settings['wallet_password']):
    print("Can't unlock wallet with password. Aborting.")
    raise SystemExit

  feed_loop(settings, market_data, wallet)


if __name__ == "__main__":
  main()
