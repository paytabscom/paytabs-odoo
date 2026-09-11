# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment_paytabs.tests.common import PayTabsCommon


@tagged('post_install', '-at_install')
class TestPaymentTransaction(PayTabsCommon):

    def test_reference_is_singularized(self):
        """ Test that the reference only contains characters allowed by PayTabs. """
        reference = self.env['payment.transaction']._compute_reference(self.provider.code)
        self.assertRegex(reference, r'^tx-\d{14}$')

    def test_paypage_payload_matches_the_transaction(self):
        """ Test that the payment page payload is built from the transaction values. """
        tx = self._create_transaction('redirect')
        payload = tx._paytabs_prepare_paypage_payload()

        self.assertEqual(payload['profile_id'], 12345)
        self.assertEqual(payload['tran_type'], 'sale')
        self.assertEqual(payload['tran_class'], 'ecom')
        self.assertEqual(payload['cart_id'], tx.reference)
        self.assertEqual(payload['cart_currency'], tx.currency_id.name)
        self.assertEqual(payload['cart_amount'], tx.amount)  # Amounts are in major units.
        self.assertTrue(payload['return'].endswith('/payment/paytabs/return'))
        self.assertTrue(payload['callback'].endswith('/payment/paytabs/webhook'))

    def test_paypage_payload_selects_a_supported_language(self):
        """ Test that the payment page language is Arabic for Arabic partners, English otherwise. """
        tx = self._create_transaction('redirect')
        for lang, expected in (('ar_001', 'ar'), ('ar_SY', 'ar'), ('fr_FR', 'en'), (False, 'en')):
            tx.partner_lang = lang
            self.assertEqual(tx._paytabs_prepare_paypage_payload()['paypage_lang'], expected)

    def test_paypage_payload_leaves_card_payments_unrestricted(self):
        """ Test that no `payment_methods` restriction is sent for card payments. """
        tx = self._create_transaction('redirect')
        self.assertNotIn('payment_methods', tx._paytabs_prepare_paypage_payload())

    def test_paypage_payload_restricts_the_page_to_the_selected_apm(self):
        """ Test that the PayTabs code of the selected APM is sent in `payment_methods`. """
        tx = self._create_transaction(
            'redirect', payment_method_id=self.env.ref('payment.payment_method_stcpay').id
        )
        self.assertEqual(tx._paytabs_prepare_paypage_payload()['payment_methods'], ['stcpay'])

    def test_paypage_payload_follows_the_hide_shipping_setting(self):
        """ Test that the `hide_shipping` flag mirrors the provider setting. """
        tx = self._create_transaction('redirect')
        self.assertTrue(tx._paytabs_prepare_paypage_payload()['hide_shipping'])
        self.provider.paytabs_hide_shipping = False
        self.assertFalse(tx._paytabs_prepare_paypage_payload()['hide_shipping'])

    def test_paypage_payload_tunnels_only_the_callback_by_default(self):
        """ Test that the tunnel URL applies to the callback URL but not to the return URL. """
        self.provider.paytabs_tunnel_url = ' https://example.ngrok-free.app/ '
        tx = self._create_transaction('redirect')
        payload = tx._paytabs_prepare_paypage_payload()
        self.assertEqual(
            payload['return'], f'{self.provider.get_base_url()}/payment/paytabs/return'
        )
        self.assertEqual(
            payload['callback'], 'https://example.ngrok-free.app/payment/paytabs/webhook'
        )

    def test_paypage_payload_tunnels_the_return_url_when_enabled(self):
        """ Test that the return URL goes through the tunnel when its toggle is enabled. """
        self.provider.write({
            'paytabs_tunnel_url': 'https://example.ngrok-free.app',
            'paytabs_tunnel_return': True,
            'paytabs_tunnel_callback': False,
        })
        tx = self._create_transaction('redirect')
        payload = tx._paytabs_prepare_paypage_payload()
        self.assertEqual(
            payload['return'], 'https://example.ngrok-free.app/payment/paytabs/return'
        )
        self.assertEqual(
            payload['callback'], f'{self.provider.get_base_url()}/payment/paytabs/webhook'
        )

    def test_paypage_payload_uses_the_base_url_without_tunnel(self):
        """ Test that the toggles have no effect while no tunnel URL is set. """
        self.provider.write({
            'paytabs_tunnel_url': False,
            'paytabs_tunnel_return': True,
            'paytabs_tunnel_callback': True,
        })
        tx = self._create_transaction('redirect')
        payload = tx._paytabs_prepare_paypage_payload()
        self.assertEqual(
            payload['return'], f'{self.provider.get_base_url()}/payment/paytabs/return'
        )
        self.assertEqual(
            payload['callback'], f'{self.provider.get_base_url()}/payment/paytabs/webhook'
        )

    def test_paypage_payload_omits_empty_customer_details(self):
        """ Test that blank customer details are not sent to PayTabs. """
        tx = self._create_transaction('redirect')
        tx.partner_city = False  # Partner values are copied from the partner on creation.
        payload = tx._paytabs_prepare_paypage_payload()
        self.assertNotIn('city', payload['customer_details'])

    def test_rendering_values_redirect_to_the_payment_page(self):
        """ Test that the rendering values point to the PayTabs payment page. """
        tx = self._create_transaction('redirect')
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.paypage_data,
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(rendering_values['api_url'], self.paypage_data['redirect_url'])
        self.assertEqual(tx.provider_reference, self.paypage_data['tran_ref'])

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_rendering_values_handle_business_errors(self):
        """ Test that an error response without a redirect URL sets the transaction in error. """
        tx = self._create_transaction('redirect')
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.error_data,
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(rendering_values, {})
        self.assertEqual(tx.state, 'error')

    def test_rendering_values_handle_http_errors(self):
        """ Test that a failing request sets the transaction in error instead of raising. """
        tx = self._create_transaction('redirect')
        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            side_effect=ValidationError("PayTabs: " + "Authentication failed"),
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(rendering_values, {})
        self.assertEqual(tx.state, 'error')

    def test_extract_reference_from_both_payload_shapes(self):
        """ Test that the reference is extracted from redirect and webhook data alike. """
        tx_model = self.env['payment.transaction']
        self.assertEqual(
            tx_model._extract_reference('paytabs', self.return_data), self.reference
        )
        self.assertEqual(
            tx_model._extract_reference('paytabs', self.webhook_data), self.reference
        )

    def test_extract_amount_data_is_skipped_for_redirect_data(self):
        """ Test that the amount check is skipped when PayTabs omits the amount. """
        tx = self._create_transaction('redirect')
        self.assertIsNone(tx._extract_amount_data(self.return_data))

    def test_extract_amount_data_uses_major_units(self):
        """ Test that the amount is read from the webhook data as-is. """
        tx = self._create_transaction('redirect')
        amount_data = tx._extract_amount_data(self.webhook_data)
        self.assertEqual(amount_data['amount'], self.amount)
        self.assertEqual(amount_data['currency_code'], self.currency.name)

    def test_apply_updates_confirms_authorized_transaction(self):
        """ Test that an authorized payment sets the transaction as done. """
        tx = self._create_transaction('redirect')
        tx._apply_updates(self.webhook_data)
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'TST2016700000692')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_sets_on_hold_transaction_in_error(self):
        """ Test that an authorization hold is set in error and reported to the merchant. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={'response_status': 'H'})
        with patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction'
            '._log_message_on_linked_documents'
        ) as log_mock:
            tx._apply_updates(payload)
        self.assertEqual(tx.state, 'error')
        self.assertTrue(any(
            "on hold" in str(call.args[0]) for call in log_mock.call_args_list
        ))

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_sets_declined_transaction_in_error(self):
        """ Test that a declined payment sets the transaction in error. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={
            'response_status': 'D', 'response_code': '316', 'response_message': "Insufficient funds"
        })
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'error')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_decline_reason_is_logged_on_linked_documents(self):
        """ Test that the gateway's decline reason is logged for the merchant, not the customer. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={
            'response_status': 'D', 'response_code': '316', 'response_message': "Insufficient funds"
        })
        with patch(
            'odoo.addons.payment.models.payment_transaction.PaymentTransaction'
            '._log_message_on_linked_documents'
        ) as log_mock:
            tx._apply_updates(payload)
        logged_messages = [str(call.args[0]) for call in log_mock.call_args_list]
        self.assertTrue(
            any("Insufficient funds (316)" in message for message in logged_messages)
        )
        self.assertNotIn("Insufficient funds", tx.state_message)

    def test_apply_updates_cancels_voided_transaction(self):
        """ Test that a voided payment sets the transaction as canceled. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={'response_status': 'V'})
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'cancel')

    def test_apply_updates_cancels_customer_cancelled_transaction(self):
        """ Test that a payment cancelled by the customer sets the transaction as canceled. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={'response_status': 'C'})
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'cancel')

    def test_apply_updates_sets_pending_transaction_as_pending(self):
        """ Test that a pending payment sets the transaction as pending. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={'response_status': 'P'})
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'pending')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_sets_error_and_expired_transactions_in_error(self):
        """ Test that the E and X statuses set the transaction in error. """
        for status in ('E', 'X'):
            tx = self._create_transaction('redirect', reference=f'{self.reference}-{status}')
            payload = dict(self.webhook_data, payment_result={'response_status': status})
            tx._apply_updates(payload)
            self.assertEqual(tx.state, 'error')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_sets_missing_status_in_error(self):
        """ Test that data without a payment status sets the transaction in error. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={})
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'error')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_ignores_follow_up_data_on_sale_transaction(self):
        """ Test that refund/void/capture/release data doesn't update a sale transaction. """
        for tran_type in ('Refund', 'Void', 'Capture', 'Release', 'refund'):
            tx = self._create_transaction('redirect', reference=f'{self.reference}-{tran_type}')
            payload = dict(self.webhook_data, tran_type=tran_type, tran_ref='OTHER')
            tx._apply_updates(payload)
            self.assertEqual(tx.state, 'draft')
            self.assertFalse(tx.provider_reference)

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_ignores_sale_data_on_refund_transaction(self):
        """ Test that sale data doesn't update a refund transaction. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        refund_tx = source_tx._create_child_transaction(self.amount, is_refund=True)
        payload = dict(self.refund_data, tran_type='Sale')
        refund_tx._apply_updates(payload)
        self.assertEqual(refund_tx.state, 'draft')

    def test_apply_updates_matches_refund_on_previous_tran_ref(self):
        """ Test that generic data referencing the source transaction confirms a refund. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        refund_tx = source_tx._create_child_transaction(self.amount, is_refund=True)
        payload = dict(
            self.refund_data, tran_type='Sale', previous_tran_ref='TST2016700000692'
        )
        with patch('odoo.addons.base.models.ir_cron.IrCron._trigger'):
            refund_tx._apply_updates(payload)
        self.assertEqual(refund_tx.state, 'done')

    def test_apply_updates_accepts_auth_data_on_sale_transaction(self):
        """ Test that non follow-up transaction types are accepted on a sale transaction. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, tran_type='Auth')
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'done')

    def test_apply_updates_processes_refund_data_on_refund_transaction(self):
        """ Test that refund data confirms a refund transaction. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        refund_tx = source_tx._create_child_transaction(self.amount, is_refund=True)
        with patch('odoo.addons.base.models.ir_cron.IrCron._trigger') as trigger_mock:
            refund_tx._apply_updates(self.refund_data)
        self.assertEqual(refund_tx.state, 'done')
        self.assertEqual(refund_tx.provider_reference, 'TST2016700000693')
        self.assertEqual(trigger_mock.call_count, 1)

    def test_apply_updates_sets_pending_refund_as_pending_and_triggers_the_cron(self):
        """ Test that a pending refund is set as pending and still schedules post-processing. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        refund_tx = source_tx._create_child_transaction(self.amount, is_refund=True)
        with patch('odoo.addons.base.models.ir_cron.IrCron._trigger') as trigger_mock:
            refund_tx._apply_updates(self.pending_refund_data)
        self.assertEqual(refund_tx.state, 'pending')
        self.assertEqual(trigger_mock.call_count, 1)

    def test_apply_updates_does_not_trigger_the_cron_for_sale_transactions(self):
        """ Test that the post-processing cron is only triggered for refunds. """
        tx = self._create_transaction('redirect')
        with patch('odoo.addons.base.models.ir_cron.IrCron._trigger') as trigger_mock:
            tx._apply_updates(self.webhook_data)
        self.assertEqual(trigger_mock.call_count, 0)

    def test_process_sets_transaction_in_error_on_amount_mismatch(self):
        """ Test that webhook data with a different amount sets the transaction in error. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, cart_amount=str(self.amount + 1))
        tx._process('paytabs', payload)
        self.assertEqual(tx.state, 'error')

    def test_process_sets_transaction_in_error_on_currency_mismatch(self):
        """ Test that webhook data with a different currency sets the transaction in error. """
        tx = self._create_transaction('redirect')
        other_currency = 'USD' if self.currency.name != 'USD' else 'EUR'
        payload = dict(self.webhook_data, cart_currency=other_currency)
        tx._process('paytabs', payload)
        self.assertEqual(tx.state, 'error')

    def test_process_confirms_transaction_from_redirect_data(self):
        """ Test that redirect data, which carries no amount, still confirms the transaction. """
        tx = self._create_transaction('redirect')
        tx._process('paytabs', self.return_data)
        self.assertEqual(tx.state, 'done')

    @mute_logger('odoo.addons.payment_paytabs.models.payment_transaction')
    def test_apply_updates_rejects_unknown_status(self):
        """ Test that an unknown payment status sets the transaction in error. """
        tx = self._create_transaction('redirect')
        payload = dict(self.webhook_data, payment_result={'response_status': 'Z'})
        tx._apply_updates(payload)
        self.assertEqual(tx.state, 'error')

    def test_apply_updates_reads_the_redirect_status(self):
        """ Test that the status is also read from the redirect data. """
        tx = self._create_transaction('redirect')
        tx._apply_updates(self.return_data)
        self.assertEqual(tx.state, 'done')

    def test_refund_request_targets_the_source_transaction(self):
        """ Test that the refund request refers to the tran_ref of the source transaction. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        refund_tx = source_tx._create_child_transaction(self.amount, is_refund=True)

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=self.refund_data,
        ) as request_mock:
            refund_tx._send_refund_request()

        payload = request_mock.call_args.kwargs['json']
        self.assertEqual(payload['tran_type'], 'refund')
        self.assertEqual(payload['tran_ref'], 'TST2016700000692')
        self.assertEqual(payload['cart_amount'], self.amount)  # Sent as a positive amount.
        self.assertEqual(refund_tx.provider_reference, 'TST2016700000693')
        self.assertEqual(refund_tx.state, 'done')

    def test_refund_request_handles_business_errors(self):
        """ Test that a refund rejected with an HTTP 200 response sets the refund in error. """
        source_tx = self._create_transaction(
            'redirect', state='done', provider_reference='TST2016700000692'
        )
        error_data = {'code': 322, 'message': "Refund not available for this transaction"}

        with patch(
            'odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request',
            return_value=error_data,
        ):
            refund_tx = source_tx._refund()

        self.assertEqual(refund_tx.state, 'error')
        self.assertIn("Refund not available", refund_tx.state_message)
        self.assertFalse(refund_tx.provider_reference)
