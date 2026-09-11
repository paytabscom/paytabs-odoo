# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Command

from odoo.addons.payment.tests.common import PaymentCommon


class PayTabsCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.provider = cls._prepare_provider('paytabs', update_values={
            'paytabs_region': 'ARE',
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
