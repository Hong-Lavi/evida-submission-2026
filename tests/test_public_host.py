"""Serving a public demo widens the host guard by exactly one name, and weakens nothing else.

check_local exists so that a page on another site cannot drive this server through the browser of
someone who has it open: the Host must be loopback, a POST must carry a header no cross-origin
form can set, and an Origin that is present must match. A public instance needs its own hostname
to pass the first of those, and nothing more.

So the allowance is an explicit list, empty by default. A name has to be configured for it to be
accepted, the matching Origin is that host over https rather than any origin, and the header and
content-type requirements are untouched. These check the widening and, more importantly, that the
parts that were not meant to widen did not.
"""
from __future__ import annotations

import unittest

from evida.server import host_allowed, origin_allowed

PUBLIC = 'namespace-fields-dennis-tuner.trycloudflare.com'


class LoopbackTests(unittest.TestCase):
    def test_loopback_is_allowed_with_nothing_configured(self):
        for host in ('127.0.0.1', '127.0.0.1:8904', 'localhost', 'localhost:8901'):
            with self.subTest(host=host):
                self.assertTrue(host_allowed(host, ()))

    def test_anything_else_is_refused_with_nothing_configured(self):
        for host in (PUBLIC, 'evil.example', '127.0.0.1.evil.example', '', 'localhost.evil.example'):
            with self.subTest(host=host):
                self.assertFalse(host_allowed(host, ()))


class PublicHostTests(unittest.TestCase):
    def test_the_configured_host_is_allowed(self):
        self.assertTrue(host_allowed(PUBLIC, (PUBLIC,)))

    def test_loopback_still_works_alongside_it(self):
        self.assertTrue(host_allowed('127.0.0.1:8904', (PUBLIC,)))

    def test_a_different_host_is_still_refused(self):
        for host in ('evil.example', 'other.trycloudflare.com', PUBLIC + '.evil.example',
                     'evil.example/' + PUBLIC):
            with self.subTest(host=host):
                self.assertFalse(host_allowed(host, (PUBLIC,)))

    def test_the_port_form_of_a_configured_host_is_accepted(self):
        self.assertTrue(host_allowed(PUBLIC + ':443', (PUBLIC,)))

    def test_matching_is_not_case_sensitive_because_host_names_are_not(self):
        self.assertTrue(host_allowed(PUBLIC.upper(), (PUBLIC,)))


class OriginTests(unittest.TestCase):
    def test_an_absent_origin_is_left_to_the_other_checks(self):
        self.assertTrue(origin_allowed(None, '127.0.0.1:8904'))

    def test_the_loopback_origin_matches_over_http(self):
        self.assertTrue(origin_allowed('http://127.0.0.1:8904', '127.0.0.1:8904'))

    def test_a_public_host_matches_over_https(self):
        self.assertTrue(origin_allowed('https://' + PUBLIC, PUBLIC))

    def test_a_foreign_origin_is_refused_even_on_the_public_host(self):
        for origin in ('https://evil.example', 'http://evil.example',
                       'https://evil.example/' + PUBLIC, 'null'):
            with self.subTest(origin=origin):
                self.assertFalse(origin_allowed(origin, PUBLIC))

    def test_a_public_host_over_plain_http_is_refused(self):
        # The demo is reached over https; an http origin for that name is not this page.
        self.assertFalse(origin_allowed('http://' + PUBLIC, PUBLIC))


if __name__ == '__main__':
    unittest.main()
