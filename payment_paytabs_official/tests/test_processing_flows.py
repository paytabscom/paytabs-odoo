# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

import json
from unittest.mock import patch

from werkzeug.exceptions import Forbidden

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_paytabs_official.controllers.main import PayTabsController
from odoo.addons.payment_paytabs_official.tests.common import PayTabsCommon


@tagged('post_install', '-at_install')
class TestProcessingFlows(PayTabsCommon, PaymentHttpCommon):

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_redirect_notification_does_not_trigger_processing(self):
        """ Test that the return route never records payment data. """
        self._create_transaction('redirect')
        url = self._build_url(PayTabsController._return_url)
        with patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._record'
        ) as record_mock:
            self._make_http_post_request(url, data=self.return_data)
        self.assertEqual(record_mock.call_count, 0)

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_redirect_notification_does_not_trigger_signature_check(self):
        """ Test that the return route does not verify signatures, as it does not process. """
        self._create_transaction('redirect')
        url = self._build_url(PayTabsController._return_url)
        with patch(
            'odoo.addons.payment_paytabs_official.controllers.main.PayTabsController._verify_signature'
        ) as signature_check_mock:
            self._make_http_post_request(url, data=self.return_data)
        self.assertEqual(signature_check_mock.call_count, 0)

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_triggers_processing(self):
        """ Test that receiving a valid webhook notification records the payment data. """
        self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        with patch(
            'odoo.addons.payment_paytabs_official.controllers.main.PayTabsController._verify_signature'
        ), patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._record'
        ) as record_mock:
            self._make_json_request(url, data=self.webhook_data)
        self.assertEqual(record_mock.call_count, 1)

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_triggers_signature_check(self):
        """ Test that receiving a webhook notification triggers a signature check. """
        self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        with patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction._record'
        ), patch(
            'odoo.addons.payment_paytabs_official.controllers.main.PayTabsController._verify_signature'
        ) as signature_check_mock:
            self._make_json_request(url, data=self.webhook_data)
        self.assertEqual(signature_check_mock.call_count, 1)

    def test_webhook_notification_with_valid_signature_confirms_the_transaction(self):
        """ Test the webhook end-to-end: real signature header on the raw body. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        raw_body = json.dumps(self.webhook_data).encode()
        signature = tx.provider_id._paytabs_calculate_signature(raw_body, is_redirect=False)
        response = self.url_open(
            url,
            data=raw_body,
            headers={'Content-Type': 'application/json', 'signature': signature},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tx.state, 'draft')  # The data is only recorded by the webhook.
        self._run_processing()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, self.webhook_data['tran_ref'])

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_with_invalid_signature_is_rejected(self):
        """ Test that a webhook notification with a bad signature header returns 403. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        raw_body = json.dumps(self.webhook_data).encode()
        response = self.url_open(
            url,
            data=raw_body,
            headers={'Content-Type': 'application/json', 'signature': 'dummy'},
        )
        self.assertEqual(response.status_code, 403)
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_without_signature_header_is_rejected(self):
        """ Test that a webhook notification without a signature header returns 403. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        response = self._make_json_request(url, data=self.webhook_data)
        self.assertEqual(response.status_code, 403)
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_without_profile_id_is_rejected(self):
        """ Test that a correctly signed webhook notification without profile ID returns 403. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        data = {k: v for k, v in self.webhook_data.items() if k != 'profile_id'}
        raw_body = json.dumps(data).encode()
        signature = tx.provider_id._paytabs_calculate_signature(raw_body, is_redirect=False)
        response = self.url_open(
            url,
            data=raw_body,
            headers={'Content-Type': 'application/json', 'signature': signature},
        )
        self.assertEqual(response.status_code, 403)
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_for_another_profile_is_rejected(self):
        """ Test that a correctly signed webhook notification for another profile returns 403. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        raw_body = json.dumps(dict(self.webhook_data, profile_id=99999)).encode()
        signature = tx.provider_id._paytabs_calculate_signature(raw_body, is_redirect=False)
        response = self.url_open(
            url,
            data=raw_body,
            headers={'Content-Type': 'application/json', 'signature': signature},
        )
        self.assertEqual(response.status_code, 403)
        self._run_processing()
        self.assertEqual(tx.state, 'draft')

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_with_malformed_body_is_rejected(self):
        """ Test that a webhook notification with a non-JSON body returns 403. """
        url = self._build_url(PayTabsController._webhook_url)
        response = self.url_open(
            url, data=b'not json', headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(response.status_code, 403)

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_webhook_notification_for_unknown_transaction_is_acknowledged(self):
        """ Test that a webhook notification for an unknown cart ID is acknowledged with 200. """
        url = self._build_url(PayTabsController._webhook_url)
        data = dict(self.webhook_data, cart_id='unknown-reference')
        response = self._make_json_request(url, data=data)
        self.assertEqual(response.status_code, 200)

    def test_webhook_notification_authorizes_the_transaction(self):
        """ Test that an 'Auth' webhook notification sets the transaction as authorized. """
        self.provider.capture_manually = True
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._webhook_url)
        raw_body = json.dumps(self.auth_webhook_data).encode()
        signature = tx.provider_id._paytabs_calculate_signature(raw_body, is_redirect=False)
        response = self.url_open(
            url,
            data=raw_body,
            headers={'Content-Type': 'application/json', 'signature': signature},
        )
        self.assertEqual(response.status_code, 200)
        self._run_processing()
        self.assertEqual(tx.state, 'authorized')

    def test_webhook_notification_for_capture_is_routed_to_the_child_transaction(self):
        """ Test that a capture webhook notification updates the capture child, idempotently. """
        source_tx = self._create_authorized_transaction()
        capture_tx = source_tx._create_child_transaction(self.amount)
        url = self._build_url(PayTabsController._webhook_url)
        raw_body = json.dumps(self.capture_data).encode()
        signature = source_tx.provider_id._paytabs_calculate_signature(raw_body, is_redirect=False)
        headers = {'Content-Type': 'application/json', 'signature': signature}
        for _i in range(2):  # PayTabs may send the same notification more than once.
            response = self.url_open(url, data=raw_body, headers=headers)
            self.assertEqual(response.status_code, 200)
        self._run_processing()
        self.assertEqual(capture_tx.state, 'done')
        self.assertEqual(capture_tx.provider_reference, 'TST2016700000694')
        self.assertEqual(source_tx.state, 'done')

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_redirect_notification_only_redirects_to_status_page(self):
        """ Test that signed return data redirects to the status page without updating the tx. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._return_url)
        data = dict(self.return_data)
        data['signature'] = tx.provider_id._paytabs_calculate_signature(data)
        response = self._make_http_post_request(url, data=data)
        self.assertEqual(response.status_code, 200)  # Redirected to /payment/status.
        self.assertTrue(response.url.endswith('/payment/status'))
        self._run_processing()
        self.assertEqual(tx.state, 'draft')  # Only the webhook updates the transaction.

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_redirect_without_data_redirects_to_status_page(self):
        """ Test that a bare GET return (plain HTTP return URL) redirects to the status page. """
        tx = self._create_transaction('redirect')
        url = self._build_url(PayTabsController._return_url)
        response = self._make_http_get_request(url)
        self.assertEqual(response.status_code, 200)  # Redirected to /payment/status.
        self.assertTrue(response.url.endswith('/payment/status'))
        self.assertEqual(tx.state, 'draft')

    def test_accept_notification_with_valid_signature(self):
        """ Test the verification of a notification with a valid signature. """
        tx = self._create_transaction('redirect')
        self._assert_does_not_raise(
            Forbidden,
            PayTabsController._verify_signature,
            self.return_data,
            tx.provider_id._paytabs_calculate_signature(self.return_data),
            tx,
        )

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_reject_notification_with_missing_signature(self):
        """ Test the verification of a notification with a missing signature. """
        tx = self._create_transaction('redirect')
        self.assertRaises(
            Forbidden, PayTabsController._verify_signature, self.return_data, None, tx
        )

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_reject_notification_with_invalid_signature(self):
        """ Test the verification of a notification with an invalid signature. """
        tx = self._create_transaction('redirect')
        self.assertRaises(
            Forbidden, PayTabsController._verify_signature, self.return_data, 'dummy', tx
        )

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_reject_tampered_redirect_notification(self):
        """ Test that altering the payment status invalidates the signature. """
        tx = self._create_transaction('redirect')
        signature = tx.provider_id._paytabs_calculate_signature(self.return_data)
        tampered_data = dict(self.return_data, respStatus='A', cartId='other-reference')
        self.assertRaises(
            Forbidden, PayTabsController._verify_signature, tampered_data, signature, tx
        )

    def test_accept_redirect_data_without_profile_id(self):
        """ Test that redirect data is accepted without a profile ID when not required. """
        tx = self._create_transaction('redirect')
        self._assert_does_not_raise(
            Forbidden, PayTabsController._verify_profile, self.return_data, tx
        )

    def test_accept_data_with_matching_profile_id(self):
        """ Test that data for the provider's own profile is accepted in both payload shapes. """
        tx = self._create_transaction('redirect')
        self._assert_does_not_raise(
            Forbidden, PayTabsController._verify_profile, self.webhook_data, tx, True
        )
        self._assert_does_not_raise(
            Forbidden,
            PayTabsController._verify_profile,
            dict(self.return_data, profileId='12345'),
            tx,
        )

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_reject_webhook_data_without_profile_id(self):
        """ Test that webhook data is rejected when the required profile ID is missing. """
        tx = self._create_transaction('redirect')
        data = {k: v for k, v in self.webhook_data.items() if k != 'profile_id'}
        self.assertRaises(Forbidden, PayTabsController._verify_profile, data, tx, True)

    @mute_logger('odoo.addons.payment_paytabs_official.controllers.main')
    def test_reject_data_for_another_profile(self):
        """ Test that data for another profile is rejected in both payload shapes. """
        tx = self._create_transaction('redirect')
        self.assertRaises(
            Forbidden,
            PayTabsController._verify_profile,
            dict(self.webhook_data, profile_id=99999),
            tx,
        )
        self.assertRaises(
            Forbidden,
            PayTabsController._verify_profile,
            dict(self.return_data, profileId='99999'),
            tx,
        )
