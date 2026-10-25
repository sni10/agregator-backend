import json
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .. import coins
from .test_public_api import story

UPSTREAM = {'bitcoin': {'usd': 80602, 'usd_24h_change': 0.6}, 'ethereum': {'usd': 2345.63, 'usd_24h_change': -1.3}}


def reply(data=UPSTREAM):
    return lambda *a, **kw: BytesIO(json.dumps(data).encode())


class MentionedTests(TestCase):
    def test_tickers_in_capitals_and_names(self):
        self.assertEqual(coins.mentioned('Bitcoin and $ETH rallied', 'SOL fell'), ['bitcoin', 'ethereum', 'solana'])

    def test_no_false_matches(self):
        self.assertEqual(coins.mentioned('Electron apps, a sol-gel, the link, Ethernet, dot com, uniform'), [])


class PricesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.urlopen = mock.patch('urllib.request.urlopen', side_effect=reply()).start()
        self.addCleanup(mock.patch.stopall)

    def test_prices_are_fetched_once_and_cached(self):
        first = self.client.get('/prices')
        self.client.get('/prices')

        self.assertEqual(first.data, [
            {'id': 'bitcoin', 'symbol': 'BTC', 'name': 'Bitcoin', 'usd': 80602.0, 'change_24h': 0.6},
            {'id': 'ethereum', 'symbol': 'ETH', 'name': 'Ethereum', 'usd': 2345.63, 'change_24h': -1.3},
        ])
        self.assertIn('max-age=60', first['Cache-Control'])
        self.assertEqual(self.urlopen.call_count, 1)
        [request], kwargs = self.urlopen.call_args
        self.assertIn('ids=bitcoin%2Cethereum%2C', request.full_url)
        self.assertEqual((request.get_header('User-agent'), kwargs), (coins.USER_AGENT, {'timeout': 5}))

    def test_coingecko_down_serves_the_last_prices_or_503(self):
        self.urlopen.side_effect = OSError('429')
        self.assertEqual(self.client.get('/prices').status_code, 503)

        self.urlopen.side_effect = reply()
        self.client.get('/prices')
        cache.delete('coins:fresh')
        self.urlopen.side_effect = OSError('429')

        self.assertEqual([row['id'] for row in self.client.get('/prices').data], ['bitcoin', 'ethereum'])

    def test_a_story_lists_the_coins_it_names(self):
        story('etf', category='crypto', body_md='Bitcoin ETFs saw outflows while ETH held.')

        self.assertEqual(self.client.get('/publications/etf').data['coins'], ['bitcoin', 'ethereum'])
