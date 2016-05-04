STEEM Price Feed: STEEM Currency Price Feed for Witnesses

Introduction
============

[STEEM Price Feed](https://github.com/steemed/steem-price-feed/) is yet another
[STEEM](https://steemit.com/) price feed for witnesses.
It has several advantages over simpler feed scripts including:

* Extensive configurability through a [YAML](http://yaml.org/) config file.
* The ability to add exchanges through the config file.
* Volume-weighted prices that proportionally reduce the influence of low volume markets.
* Stochastic update based on variance analysis of price history.


Stochastic Updating
-------------------

One innovation of STEEM Price Feed is that the decision to update at
any cycle is probabilistic. If the current estimated price satisfies the
"hard" publication criteria (exceeds a minimum price fluctation
and minimum waiting period), then the variance of the feed history
is calculated and the current price is converted to a
[z-score](https://en.wikipedia.org/wiki/Standard_score). This score is
converted to a cumulative probability using the
[standard error function](https://en.wikipedia.org/wiki/Error_function)
and if a random number in the interval `[0,1)` is less than the cumulative
probability, then the current price estimate is published. If not,
then STEEM Price Feed tries again after a waiting period.


Dependencies
============

STEEM Price Feed has only two dependencies: [PyYaml](http://pyyaml.org/) and
[Requests](http://docs.python-requests.org/).
On [Ubuntu](http://www.ubuntu.com/), these dependencies
can be installed with the following command:

```
sudo apt-get install python-yaml python-requests
```

Configuration
=============

An example configuration file is provided in the `examples` directory as `feed-example.yaml`.
The configuration file is specified when calling the `steem-price-feed.py` script:

```
python steem-price-feed.py /home/ima/steem/feed.yaml
```

Although the instructions below may appear intimidating,
**only a couple of settings at the top of the configuration file actually need to be changed**.
These settings are

* `witness_name`
* `wallet_password`
* `rpc_user`
* `rpc_password`

It is perfectly reasonable to take the rest of the settings as the defaults.

The configuration file has two main sections, `settings` and `market_data`.

Section: `settings`
------------------

The settings are

* **`witness_name`**: the witness name (e.g. *steemed*)
* **`wallet_password`**: the witness password
* **`min_publish_interval`** : do not publish a new feed if it has not been this many *hours* since the last
* **`max_publish_interval`** : pulish a new feed if this many *hours* have passed since the last publication
* **`rpc_ip`**: the ip that the wallet server (`cli_wallet`) runs on (e.g. `127.0.0.1`)
* **`rpc_port`**: the port that the wallet server runs on (e.g. `8091`)
* **`rpc_user`**: the user set for `cli_wallet` using the `--server-rpc-user` flag
* **`rpc_password`**: the password set for `cli_wallet` using the `--server-rpc-password` flag
* **`default_base`**: a base price for 1 STEEM, denominated in SBD; used if all else fails
* **`log_file`**: *optional*; a file to print errors and debugging information;
if not provided, `stdout` will be used (default: `null`)
* **`debug`**: *optional*; emit debugging information if set to `true` (default: `false`)

Section: `market_data`
----------------------

Market data subsections are market pairs, expressed as `query_base`, where `query` is the asset
that is priced in terms of the `base` asset. For example, the `btc_usd` subsection means that
BTC pricing information will be reported in terms of USD. Volume will be reported in terms of BTC (`query`).

Each `market_data` subsection has sub-subsections for each exchange. For example, current `btc_usd` exchanges
are `bitfinex`, `coinbase`, `okcoin`, `bitstamp`. Each exchange has two subsections, `price` and `volume`
that specify how to retrieve these amounts. Key-value pairs for `price` and `volume` are:

* **`url`**: the base API url for the query (e.g. `https://www.okcoin.com/api/v1/ticker.do`)
* **`query_params`**: form query parameters used for http GET, express as a JSON object (e.g. `{"symbol": "btc_usd"}`)
* **`accessor`**: specifies how to traverse the JSON object to extract the needed information,
expressed as a list of object members (keys) and/or array indices, intermingled

### Example of `market_data`

An example of a `market_data` for the [OKCoin](https://www.okcoin.com/) subsection is:

```
market_data :
  btc_usd :
    ...
    okcoin :
      price :
        url : "https://www.okcoin.com/api/v1/ticker.do"
        query_params :
           {"symbol": "btc_usd"}
        accessor : ["ticker", "last"]
      volume :
        url : "https://www.okcoin.com/api/v1/ticker.do"
        query_params : {"symbol": "btc_usd"}
        accessor : ["ticker", "vol"]
```

#### Query URL and `query_params`

To query the BTC:USD price for OKCoin, this configuration specifies the URL

[https://www.okcoin.com/api/v1/ticker.do?symbol:btc_usd](https://www.okcoin.com/api/v1/ticker.do?symbol:btc_usd)

Notice how the `query_params`were appended as form submission data to the URL:

```
query_params : {"symbol": "btc_usd"}
```

#### Accessing the JSON: `acessor`

The *formatted* JSON returned by this query as of the time of writing these instructions is:

```
{
  "date":"1462307028",
  "ticker": {
              "buy":"449.25", "high":"449.62", "last":"449.25",
              "low":"440.75", "sell":"449.4", "vol":"10025.1961"
            }
}
```

Assuming the  JSON object representing this result is called `OK`, accessing the last price
would look like:

```
OK["ticker"]["last"]
```

This corresponds to the `acessor` provided for the query in the YAML configuration file:

```
accessor: ["ticker", "last"]
```

Because the syntax of accessing array elements is exactly the same as accessing object members
except that member names are strings and array indices are integers, the `accessor` allows
simply mixing member names and array indices. For example, as of the time of writing these
instructions, the *formatted* [Bittrex](https://bittrex.com) market summary for STEEM is:

```
{
  "success":true,
  "message":"",
  "result":
  [
    {
      "MarketName":"BTC-STEEM", "High":0.00120025, "Low":0.00090000,
      "Volume":35316.37017575, "Last":0.00107443, "BaseVolume":34.61316041,
      "TimeStamp":"2016-05-03T20:35:41.713", "Bid":0.00097042, "Ask":0.00105730,
      "OpenBuyOrders":105, "OpenSellOrders":341, "PrevDay":0.00109784,
      "Created":"2016-04-17T01:22:13.35"
    }
  ]
}
```

Notice that this API call has a single element array that contains all of the BTC:STEEM market
information. If this JSON object were called `TREX`, then the volume information would be accessed
like this:

```
TREX["result"][0]["Volume"]
```

The corresponding `accessor` line would then be

```
accessor : ["result", 0, "Volume"]
```

Usage
=====

The STEEM Price Feed service is meant to be run as a daemon, although it can easily
be run manually like a normal python script for debugging.

The services `steem-cli` and `steem-price-feed` will start on boot if properly configured.
Their setup is described below.

If stopped, these services can be started with the following commands after they are set up:

```
sudo service steem-cli start
sudo service steem-price-feed start
```

These commands assume that a suitable `steemd` instance is running and listening at
the default RPC port.

Upstart Service `steem-cli`
---------------------------

Because publishing a price feed requires an open wallet, an instance of `cli_wallet` must
be run as a daemon process, listening on an RPC port. On Ubuntu,
this is best achieved using [Upstart](http://upstart.ubuntu.com/) services.

To create an Upstart service for `cli_wallet`, add this simple initialization file at `/etc/init/steem-cli.conf`
(edited for your system, especially changing the password to something very strong):

```
# steem-cli service - steem cli_wallet service for witness

description "Steem CLI"
author "Ima Witness <ima@example.com>"

# Stanzas
#
# Stanzas control when and how a process is started and stopped
# See a list of stanzas here: //upstart.ubuntu.com/wiki/Stanzas

# When to start the service
start on runlevel [2345]

# When to stop the service
stop on runlevel [016]

# Automatically restart process if crashed
respawn

# Essentially lets upstart know the process will detach itself to the background
# This option does not seem to be of great importance, so it does not need to be set.
# expect fork

# Specify working directory
chdir /home/ima/steem

# Specify the process/command to start, e.g.
exec ./cli_wallet -u user -p password \
                --rpc-endpoint=127.0.0.1:8091 -d 2>cli-debug.log 1>cli-error.log
```

Upstart Service `steem-price-feed`
----------------------------------

Similarly, it is desirable for STEEM Price Feed (`steem-price-feed.py`) to
run as an upstart service so that it starts on reboot and respawns in case
it is terminated undesirably.

Put the following file at `/etc/init/steem-price-feed.conf` (edited for your
own system).

```
# steem-price-feed service - steem-price-feed service for witness

description "STEEM Price Feed"
author "Ima Witness <ima@example.com>"

# Stanzas
#
# Stanzas control when and how a process is started and stopped
# See a list of stanzas here: //upstart.ubuntu.com/wiki/Stanzas

# When to start the service
start on runlevel [2345]

# When to stop the service
stop on runlevel [016]

# Automatically restart process if crashed
respawn

# Essentially lets upstart know the process will detach itself to the background
# This option does not seem to be of great importance, so it does not need to be set.
# expect fork

# Specify working directory
chdir /home/ima/steem

# Specify the process/command to start, e.g.
exec /usr/bin/python steem-price-feed.py feed.yaml 2>feed-debug.log 1>feed-error.log
```
