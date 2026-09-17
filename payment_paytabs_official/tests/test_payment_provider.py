# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

import hashlib
import hmac
from unittest.mock import Mock, patch

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import is_html_empty

from odoo.addons.payment_paytabs_official import const
from odoo.addons.payment_paytabs_official.tests.common import PayTabsCommon


@tagged('post_install', '-at_install')
class TestPaymentProvider(PayTabsCommon):

    def test_provider_supports_partial_refunds(self):
        """ Test that PayTabs providers support partial refunds. """
        self.assertEqual(self.provider.support_refund, 'partial')

    def test_provider_supports_partial_manual_capture(self):
        """ Test that PayTabs providers support partial manual capture. """
        self.assertEqual(self.provider.support_manual_capture, 'partial')

    def test_manual_capture_can_be_enabled_with_cards(self):
        """ Test that manual capture can be enabled when only cards are linked. """
        self.provider.capture_manually = True
        self.assertTrue(self.provider.capture_manually)

    def test_manual_capture_is_refused_with_unsupported_payment_methods(self):
        """ Test that manual capture can't be enabled with payment methods that don't support it. """
        mada = self.env.ref('payment.payment_method_mada')
        mada.active = True  # The constraint only considers active payment methods.
        self.provider.payment_method_ids = [Command.link(mada.id)]
        with self.assertRaises(ValidationError):
            self.provider.capture_manually = True

    def test_default_payment_method_codes_include_card(self):
        """ Test that cards are enabled by default when PayTabs is enabled. """
        self.assertIn('card', self.provider._get_default_payment_method_codes())

    def test_request_url_is_built_from_the_endpoint(self):
        """ Test that the API URL matches the endpoint of the PayTabs account. """
        self.assertEqual(
            self.provider._build_request_url('payment/request'),
            'https://secure.paytabs.com/payment/request',
        )

        self.provider.paytabs_endpoint = 'SAU'
        self.assertEqual(
            self.provider._build_request_url('payment/request'),
            'https://secure.paytabs.sa/payment/request',
        )

    def test_every_endpoint_has_an_api_url(self):
        """ Test that each selectable endpoint maps to an API URL, and vice versa. """
        endpoint_codes = {
            code for code, _label in self.provider._fields['paytabs_endpoint'].selection
        }
        self.assertEqual(endpoint_codes, set(const.API_URLS))
        for endpoint in endpoint_codes:
            self.provider.paytabs_endpoint = endpoint
            self.assertEqual(
                self.provider._build_request_url('payment/request'),
                f'{const.API_URLS[endpoint]}/payment/request',
            )

    def test_endpoint_does_not_depend_on_the_provider_state(self):
        """ Test that test and live providers use the same endpoint. """
        self.provider.state = 'test'
        test_url = self.provider._build_request_url('payment/request')
        self.provider.state = 'enabled'
        self.assertEqual(self.provider._build_request_url('payment/request'), test_url)

    def test_request_url_is_built_with_a_leading_slash(self):
        """ Test that endpoints are joined to the base URL without doubling the slash. """
        self.assertEqual(
            self.provider._build_request_url('/payment/request'),
            'https://secure.paytabs.com/payment/request',
        )

    def test_request_headers_include_the_server_key(self):
        """ Test that the server key is sent as the authorization header. """
        headers = self.provider._build_request_headers('POST', 'payment/request', {})
        self.assertEqual(headers['Authorization'], self.provider.paytabs_server_key)

    def test_request_url_raises_a_clear_error_for_an_unknown_endpoint(self):
        """ Test that unknown endpoints fail with a configuration error instead of a KeyError. """
        # The ORM rejects values outside the selection, so drop the mapping instead.
        with patch.dict(const.API_URLS, clear=True), \
             self.assertRaisesRegex(ValueError, 'Unknown PayTabs endpoint'):
            self.provider._build_request_url('payment/request')

    def test_redirect_signature_ignores_empty_and_signature_fields(self):
        """ Test that the redirect signature is computed on the sorted, non-empty fields. """
        signature = self.provider._paytabs_calculate_signature(
            {'b': 'two', 'a': 'one', 'empty': '', 'null': None, 'signature': 'ignored'}
        )
        # Equivalent to hmac_sha256('a=one&b=two', server_key).
        expected_signature = self.provider._paytabs_calculate_signature({'a': 'one', 'b': 'two'})
        self.assertEqual(signature, expected_signature)

    def test_redirect_signature_keeps_zero_valued_fields(self):
        """ Test that a '0' value is part of the signed payload.

        Dropping falsy-but-present values is the classic cause of a permanently failing signature.
        """
        self.assertNotEqual(
            self.provider._paytabs_calculate_signature({'a': 'one', 'zero': '0'}),
            self.provider._paytabs_calculate_signature({'a': 'one'}),
        )

    def test_redirect_signature_matches_the_reference_implementation(self):
        """ Test the signed query string against the PayTabs reference test vector. """
        signing_string = (
            'cartId=CART%231001&customerEmail=customer%40example.com&customerName=First+Last'
            '&hideShipping=0&respCode=G14033&respMessage=Authorised&respStatus=A'
            '&tranRef=TST2306001234567'
        )
        self.provider.paytabs_server_key = 'SJJ9MRLDJN-JGHZRT2LKD-B6RTNKKW6L'
        self.assertEqual(
            self.provider._paytabs_calculate_signature({
                'tranRef': 'TST2306001234567',
                'cartId': 'CART#1001',
                'respStatus': 'A',
                'respCode': 'G14033',
                'respMessage': 'Authorised',
                'customerEmail': 'customer@example.com',
                'customerName': 'First Last',
                'hideShipping': '0',
                'token': '',
                'acquirerMessage': None,
                'signature': 'PLACEHOLDER',
            }),
            hmac.new(
                self.provider.paytabs_server_key.encode(),
                msg=signing_string.encode(),
                digestmod=hashlib.sha256,
            ).hexdigest(),
        )

    def test_redirect_signature_url_encodes_the_values(self):
        """ Test that the signed query string is URL-encoded like PayTabs does. """
        self.assertEqual(
            self.provider._paytabs_calculate_signature({'msg': 'a b&c'}),
            hmac.new(
                self.provider.paytabs_server_key.encode(),
                msg=b'msg=a+b%26c',
                digestmod=hashlib.sha256,
            ).hexdigest(),
        )

    def test_webhook_signature_is_computed_on_the_raw_body(self):
        """ Test that the webhook signature is computed on the raw request body. """
        body = b'{"tran_ref": "TST2016700000692"}'
        self.assertEqual(
            self.provider._paytabs_calculate_signature(body, is_redirect=False),
            hmac.new(
                self.provider.paytabs_server_key.encode(), msg=body, digestmod=hashlib.sha256
            ).hexdigest(),
        )

    def test_webhook_signature_matches_the_reference_implementation(self):
        """ Test the webhook signature against the PayTabs reference test vector. """
        self.provider.paytabs_server_key = 'SJJ9MRLDJN-JGHZRT2LKD-B6RTNKKW6L'
        raw_body = (
            b'{"tran_ref":"TST2306001234567","cart_id":"CART#1001","cart_amount":"250.20",'
            b'"cart_currency":"SAR","payment_result":{"response_status":"A",'
            b'"response_code":"G14033","response_message":"Authorised"}}'
        )
        self.assertEqual(
            self.provider._paytabs_calculate_signature(raw_body, is_redirect=False),
            '0062626e080b6a271e63d6a581c01f18b60c682f540e7f15a1a6c1b2f3823376',
        )

    def test_response_error_includes_the_error_code(self):
        """ Test that the PayTabs error code is appended to the error message. """
        response = Mock(json=Mock(return_value={'code': 1, 'message': "Authentication failed"}))
        self.assertEqual(
            self.provider._parse_response_error(response), "Authentication failed (code 1)"
        )

    def test_response_error_without_code(self):
        """ Test that the error message is returned as-is when no code is provided. """
        response = Mock(json=Mock(return_value={'message': "Unknown error"}))
        self.assertEqual(self.provider._parse_response_error(response), "Unknown error")

    def _render_card_method_label(self):
        card_pm = self.env.ref('payment.payment_method_card')
        html = self.env['ir.qweb']._render('payment.method_form', {
            'pm_sudo': card_pm,
            'providers_sudo': self.provider,
            'is_selected': False,
            'mode': 'payment',
            'show_tokenize_input_mapping': {self.provider.id: False},
            'is_html_empty': is_html_empty,
        })
        return str(html)

    def test_card_method_label_defaults_to_the_method_name(self):
        """ Test that the Card method keeps its standard name when no label is configured. """
        self.provider.paytabs_card_label = False
        self.assertIn('>Card</label>', self._render_card_method_label())

    def test_card_method_label_is_replaced_at_checkout(self):
        """ Test that the configured label replaces the Card method name at checkout. """
        self.provider.paytabs_card_label = "PayTabs Payments"
        html = self._render_card_method_label()
        self.assertIn('>PayTabs Payments</label>', html)
        self.assertNotIn('>Card</label>', html)
