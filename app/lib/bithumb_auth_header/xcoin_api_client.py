import base64
import hashlib
import hmac
import math
import time
import urllib.parse
import httpx


class XCoinAPI:
    api_url = "https://api.bithumb.com"
    api_key = ""
    api_secret = ""

    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret

    def microtime(self, get_as_float=False):
        if get_as_float:
            return time.time()
        else:
            return "%f %d" % math.modf(time.time())

    def usec_time(self):
        mt = self.microtime(False)
        mt_array = mt.split(" ")[:2]
        return mt_array[1] + mt_array[0][2:5]

    async def xcoin_api_call(self, endpoint, rg_params):
        uri_array = {"endpoint": endpoint, **rg_params}
        str_data = urllib.parse.urlencode(uri_array)

        nonce = self.usec_time()
        data = endpoint + chr(0) + str_data + chr(0) + nonce
        utf8_data = data.encode("utf-8")

        key = self.api_secret
        utf8_key = key.encode("utf-8")

        h = hmac.new(bytes(utf8_key), utf8_data, hashlib.sha512)
        hex_output = h.hexdigest()
        utf8_hex_output = hex_output.encode("utf-8")

        api_sign = base64.b64encode(utf8_hex_output)
        utf8_api_sign = api_sign.decode("utf-8")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Api-Key": self.api_key,
            "Api-Nonce": nonce,
            "Api-Sign": utf8_api_sign,
        }

        url = self.api_url + endpoint

        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, data=rg_params)
            return r.json()
