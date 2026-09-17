# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment_paytabs_official.tests.common import PayTabsCommon


@tagged('post_install', '-at_install')
class TestPaymentToken(PayTabsCommon):

    # === TOKEN CREATION === #

    def test_paypage_payload_requests_tokenization(self):
        """ Test that the payment page is asked to save the payment method when requested. """
        tx = self._create_transaction('redirect', tokenize=True)
        self.assertEqual(tx._paytabs_prepare_paypage_payload()['tokenise'], 2)

    def test_paypage_payload_does_not_request_tokenization_by_default(self):
        """ Test that the payment method is not saved unless requested. """
        tx = self._create_transaction('redirect')
        self.assertNotIn('tokenise', tx._paytabs_prepare_paypage_payload())

    def test_extract_token_values_from_webhook_data(self):
        """ Test that the token values are read from the webhook data. """
        tx = self._create_transaction('redirect', tokenize=True)
        token_values = tx._extract_token_values(self.tokenized_webhook_data)
        self.assertEqual(token_values, {
            'provider_ref': self.token_value,
            'payment_details': '1111',
            'paytabs_tran_ref': 'TST2016700000692',
        })

    def test_extract_token_values_keeps_the_wallet_last_digits(self):
        """ Test that only the trailing digits of a wallet description are kept. """
        tx = self._create_transaction('redirect', tokenize=True)
        payment_data = dict(
            self.tokenized_webhook_data,
            payment_info={'payment_method': 'ApplePay', 'payment_description': 'Visa 3619'},
        )
        self.assertEqual(tx._extract_token_values(payment_data)['payment_details'], '3619')

    def test_extract_token_values_falls_back_on_the_description(self):
        """ Test that a description without trailing digits is kept as is. """
        tx = self._create_transaction('redirect', tokenize=True)
        payment_data = dict(
            self.tokenized_webhook_data, payment_info={'payment_description': 'Visa'}
        )
        self.assertEqual(tx._extract_token_values(payment_data)['payment_details'], 'Visa')

    def test_extract_token_values_ignores_redirect_data(self):
        """ Test that no token is created from the redirect data, which lacks payment info. """
        tx = self._create_transaction('redirect', tokenize=True)
        self.assertEqual(tx._extract_token_values(self.tokenized_return_data), {})

    def test_extract_token_values_ignores_data_without_token(self):
        """ Test that no token is created when PayTabs did not return one. """
        tx = self._create_transaction('redirect', tokenize=True)
        self.assertEqual(tx._extract_token_values(self.webhook_data), {})

    def test_extract_token_values_ignores_the_echoed_token(self):
        """ Test that a payment made with a token does not create the same token again. """
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id, tokenize=True)
        self.assertEqual(tx._extract_token_values(self.recurring_data), {})

    def test_process_creates_the_token_from_webhook_data(self):
        """ Test that processing the webhook data of a tokenized payment creates the token. """
        tx = self._create_transaction('redirect', tokenize=True)
        tx._process('paytabs', self.tokenized_webhook_data)
        self.assertEqual(tx.state, 'done')
        self.assertFalse(tx.tokenize)
        self.assertTrue(tx.token_id)
        self.assertEqual(tx.token_id.provider_ref, self.token_value)
        self.assertEqual(tx.token_id.payment_details, '1111')
        self.assertEqual(tx.token_id.paytabs_tran_ref, 'TST2016700000692')
        self.assertEqual(tx.token_id.partner_id, tx.partner_id)
        self.assertEqual(tx.token_id.payment_method_id, tx.payment_method_id)

    def test_process_does_not_create_a_token_when_not_requested(self):
        """ Test that a token returned for a payment not meant to be saved is ignored. """
        tx = self._create_transaction('redirect')
        tx._process('paytabs', self.tokenized_webhook_data)
        self.assertEqual(tx.state, 'done')
        self.assertFalse(tx.token_id)

    # === PAYMENTS WITH A TOKEN === #

    def test_payment_request_charges_the_token(self):
        """ Test that a payment with a token is a recurring request referencing the token. """
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.recurring_data,
        ) as request_mock:
            tx._send_payment_request()

        self.assertEqual(request_mock.call_args.args[:2], ('POST', 'payment/request'))
        payload = request_mock.call_args.kwargs['json']
        self.assertEqual(payload['profile_id'], 12345)
        self.assertEqual(payload['tran_type'], 'sale')
        self.assertEqual(payload['tran_class'], 'recurring')
        self.assertEqual(payload['cart_id'], tx.reference)
        self.assertEqual(payload['cart_currency'], self.currency.name)
        self.assertEqual(payload['cart_amount'], self.amount)
        self.assertEqual(payload['token'], self.token_value)
        self.assertEqual(payload['tran_ref'], 'TST2016700000692')
        self.assertEqual(payload['plugin_info']['cart_name'], 'odoo')
        self.assertNotIn('return', payload)
        self.assertNotIn('callback', payload)
        self.assertNotIn('tokenise', payload)
        self.assertEqual(tx.provider_reference, 'TST2016700000696')
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.token_id, token)

    def test_payment_request_authorizes_when_capturing_manually(self):
        """ Test that a payment with a token only authorizes the amount with manual capture. """
        self.provider.capture_manually = True
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id)
        response = dict(self.recurring_data, tran_type='Auth')

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=response,
        ) as request_mock:
            tx._send_payment_request()

        self.assertEqual(request_mock.call_args.kwargs['json']['tran_type'], 'auth')
        self.assertEqual(tx.state, 'authorized')

    def test_payment_request_handles_business_errors(self):
        """ Test that a token payment rejected with an HTTP 200 response raises an error. """
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.recurring_error_data,
        ), self.assertRaises(ValidationError) as error:
            tx._send_payment_request()

        self.assertIn("combination not supported", str(error.exception))
        self.assertIn("112", str(error.exception))
        self.assertFalse(tx.provider_reference)

    def test_payment_request_requires_a_token(self):
        """ Test that a payment request without a token is refused. """
        tx = self._create_transaction('redirect')
        with self.assertRaises(ValidationError):
            tx._send_payment_request()

    @mute_logger('odoo.addons.payment.models.payment_transaction')
    def test_charge_with_token_sets_rejected_transaction_in_error(self):
        """ Test that a rejected token payment ends up in error with the rejection reason. """
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.recurring_error_data,
        ):
            tx._charge_with_token()

        self.assertEqual(tx.state, 'error')
        self.assertIn("combination not supported", tx.state_message)

    @mute_logger('odoo.addons.payment_paytabs_official.models.payment_transaction')
    def test_declined_token_payment_is_set_in_error(self):
        """ Test that a declined token payment is processed as an error. """
        token = self._create_paytabs_token()
        tx = self._create_transaction('token', token_id=token.id)
        response = dict(self.recurring_data, payment_result={
            'response_status': 'D',
            'response_code': '302',
            'response_message': 'Declined',
        })

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=response,
        ):
            tx._send_payment_request()

        self.assertEqual(tx.provider_reference, 'TST2016700000696')
        self.assertEqual(tx.state, 'error')

    # === TOKEN DELETION === #

    def test_archiving_deletes_the_token_on_paytabs(self):
        """ Test that archiving a token deletes it on PayTabs. """
        token = self._create_paytabs_token()

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value={'code': 0, 'message': 'success'},
        ) as request_mock:
            token.action_archive()

        self.assertEqual(request_mock.call_args.args[:2], ('POST', 'payment/token/delete'))
        self.assertEqual(
            request_mock.call_args.kwargs['json'], {'profile_id': 12345, 'token': self.token_value}
        )
        self.assertFalse(token.active)

    @mute_logger('odoo.addons.payment_paytabs_official.models.payment_token')
    def test_archiving_tolerates_deletion_failures(self):
        """ Test that a token is archived even when PayTabs could not delete it. """
        token = self._create_paytabs_token()

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            side_effect=ValidationError("PayTabs: The token does not exist"),
        ):
            token.action_archive()

        self.assertFalse(token.active)

    def test_archiving_an_archived_token_does_not_call_paytabs(self):
        """ Test that archiving an already archived token sends no deletion request. """
        token = self._create_paytabs_token(active=False)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request'
        ) as request_mock:
            token.action_archive()

        request_mock.assert_not_called()
