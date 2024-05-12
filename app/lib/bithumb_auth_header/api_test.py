#! /usr/bin/env python
# XCoin API-call sample script (for Python 3.X)
#
# @author	btckorea
# @date	2017-04-11
#
#
# First, Build and install pycurl with the following commands::
# (if necessary, become root)
#
# https://pypi.python.org/pypi/pycurl/7.43.0#downloads
#
# tar xvfz pycurl-7.43.0.tar.gz
# cd pycurl-7.43.0
# python setup.py --libcurl-dll=libcurl.so install
# python setup.py --with-openssl install
# python setup.py install

from xcoin_api_client1 import XCoinAPI

api_key = "api_connect_key"
api_secret = "api_secret_key"

api = XCoinAPI(api_key, api_secret)


rgParams = {
    "endpoint": "/info/ticker",  # <-- endpoint가 가장 처음으로 와야 한다.
    "order_currency": "BTC",
}

result = api.xcoinApiCall(rgParams["endpoint"], rgParams)
print(result)
