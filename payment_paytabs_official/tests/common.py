# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

from odoo.fields import Command

from odoo.addons.payment.tests.common import PaymentCommon


class PayTabsCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.provider = cls._prepare_provider('paytabs', update_values={
            'paytabs_endpoint': 'ARE',
            'paytabs_profile_id': 12345,
            'paytabs_server_key': 'SJKLMNOPQR-XYZABCDEFG-HIJKLMNOPQ',
            'payment_method_ids': [Command.set([cls.env.ref('payment.payment_method_card').id])],
        })

        cls.paypage_data = {
            'tran_ref': 'TST2016700000692',
            'tran_type': 'Sale',
            'cart_id': cls.reference,
            'cart_description': cls.reference,
            'cart_currency': cls.currency.name,
            'cart_amount': str(cls.amount),
            'redirect_url': 'https://secure.paytabs.com/payment/page/ABC123',
            'serviceId': 2,
            'profileId': 12345,
        }
        cls.return_data = {
            'acquirerMessage': 'Authorised',
            'acquirerRRN': '123456789012',
            'cartId': cls.reference,
            'respCode': 'G31822',
            'respMessage': 'Authorised',
            'respStatus': 'A',
            'tranRef': 'TST2016700000692',
            'signature': 'fake_signature',
        }
        cls.webhook_data = {
            'tran_ref': 'TST2016700000692',
            'tran_type': 'Sale',
            'profile_id': 12345,
            'cart_id': cls.reference,
            'cart_description': cls.reference,
            'cart_currency': cls.currency.name,
            'cart_amount': str(cls.amount),
            'payment_result': {
                'response_status': 'A',
                'response_code': 'G31822',
                'response_message': 'Authorised',
                'transaction_time': '2025-01-01T00:00:00Z',
            },
            'payment_info': {
                'payment_method': 'Visa',
                'card_scheme': 'Visa',
                'payment_description': '4111 11## #### 1111',
            },
        }
        cls.refund_data = {
            'tran_ref': 'TST2016700000693',
            'tran_type': 'Refund',
            'profile_id': 12345,
            'cart_id': f'R-{cls.reference}',
            'cart_currency': cls.currency.name,
            'cart_amount': str(cls.amount),
            'payment_result': {
                'response_status': 'A',
                'response_code': 'G31823',
                'response_message': 'Authorised',
            },
        }
        cls.pending_refund_data = dict(cls.refund_data, payment_result={
            'response_status': 'P',
            'response_code': 'G31824',
            'response_message': 'Pending',
        })
        cls.error_data = {
            'code': 4,
            'message': "Duplicate request",
        }
        cls.auth_webhook_data = dict(cls.webhook_data, tran_type='Auth')
        cls.capture_data = {
            'tran_ref': 'TST2016700000694',
            'tran_type': 'Capture',
            'previous_tran_ref': 'TST2016700000692',
            'profile_id': 12345,
            'cart_id': f'P-{cls.reference}',
            'cart_currency': cls.currency.name,
            'cart_amount': str(cls.amount),
            'payment_result': {
                'response_status': 'A',
                'response_code': 'G31825',
                'response_message': 'Authorised',
            },
        }
        cls.void_data = dict(cls.capture_data, tran_ref='TST2016700000695', tran_type='Void')
        cls.follow_up_error_data = dict(cls.capture_data, payment_result={
            'response_status': 'E',
            'response_code': '120',
            'response_message': 'Previous transaction is on hold',
        })
        cls.token_value = '2C4A5B6D7E8F9A0B1C2D3E4F5A6B7C8D'
        cls.tokenized_webhook_data = dict(cls.webhook_data, token=cls.token_value)
        cls.tokenized_return_data = dict(cls.return_data, token=cls.token_value)
        cls.recurring_data = {
            'tran_ref': 'TST2016700000696',
            'tran_type': 'Sale',
            'tran_class': 'C/Auth',
            'previous_tran_ref': 'TST2016700000692',
            'profile_id': 12345,
            'cart_id': cls.reference,
            'cart_currency': cls.currency.name,
            'cart_amount': str(cls.amount),
            'token': cls.token_value,
            'payment_result': {
                'response_status': 'A',
                'response_code': 'G31826',
                'response_message': 'Authorised',
            },
            'payment_info': {
                'payment_method': 'Visa',
                'card_scheme': 'Visa',
                'payment_description': '4111 11## #### 1111',
            },
        }
        cls.recurring_error_data = {
            'code': 112,
            'message': "Method/Class/Currency combination not supported",
        }

    def _create_authorized_transaction(self, **values):
        """ Create an authorized transaction on a provider configured for manual capture. """
        self.provider.capture_manually = True
        return self._create_transaction(
            'redirect', state='authorized', provider_reference='TST2016700000692', **values
        )

    def _create_paytabs_token(self, **values):
        """ Create a PayTabs token carrying the reference of the transaction that created it. """
        return self._create_token(
            provider_ref=self.token_value,
            payment_details='1111',
            paytabs_tran_ref='TST2016700000692',
            **values,
        )
