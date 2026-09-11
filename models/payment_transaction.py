# Part of Odoo. See LICENSE file for full copyright and licensing details.

from urllib.parse import parse_qsl, urlsplit

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import urls

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_paytabs import const
from odoo.addons.payment_paytabs.controllers.main import PayTabsController


_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _compute_reference(self, provider_code, prefix=None, separator='-', **kwargs):
        """ Override of `payment` to ensure that PayTabs' requirements for references are satisfied.

        The reference is sent as the cart ID, which PayTabs echoes back in the notifications and
        uses in its duplicate-request detection. The prefix is generated with 'tx' as default to
        keep the reference short and to prevent it from being based on document names that may
        contain special characters (e.g. INV/2020/...).

        :param str provider_code: The code of the provider handling the transaction.
        :param str prefix: The custom prefix used to compute the full reference.
        :param str separator: The custom separator used to separate the prefix from the suffix.
        :return: The unique reference for the transaction.
        :rtype: str
        """
        if provider_code == 'paytabs':
            prefix = payment_utils.singularize_reference_prefix()
        return super()._compute_reference(
            provider_code, prefix=prefix, separator=separator, **kwargs
        )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return PayTabs-specific rendering values.

        Note: self.ensure_one() from `_get_rendering_values`.

        :param dict processing_values: The generic processing values of the transaction.
        :return: The dict of provider-specific rendering values.
        :rtype: dict
        """
        if self.provider_code != 'paytabs':
            return super()._get_specific_rendering_values(processing_values)

        # Create the hosted payment page and retrieve its URL.
        payload = self._paytabs_prepare_paypage_payload()
        try:
            payment_data = self._send_api_request('POST', 'payment/request', json=payload)
        except ValidationError as error:
            self._set_error(str(error))
            return {}

        # PayTabs reports business errors with an HTTP 200 status and no redirect URL.
        api_url = payment_data.get('redirect_url')
        if not api_url:
            _logger.warning(
                "Could not create the payment page for transaction %s. Reason: %s (code %s,"
                " trace %s)",
                self.reference,
                payment_data.get('message'),
                payment_data.get('code'),
                payment_data.get('trace'),
            )
            self._set_error(_(
                "An error occurred during the processing of your payment. Please try again."
            ))
            return {}

        # The provider reference is set to allow refunding the transaction later on.
        self.provider_reference = payment_data.get('tran_ref')

        # Extract the payment link URL and params and embed them in the redirect form.
        url_params = dict(parse_qsl(urlsplit(api_url).query))
        return {'api_url': api_url, 'url_params': url_params}

    def _paytabs_prepare_paypage_payload(self):
        """ Create the payload for the payment page request based on the transaction values.

        Note: `self.ensure_one()`

        :return: The request payload.
        :rtype: dict
        """
        self.ensure_one()

        return_base_url = self.provider_id._paytabs_get_public_base_url('return')
        callback_base_url = self.provider_id._paytabs_get_public_base_url('callback')
        customer_details = {
            'name': self.partner_name,
            'email': self.partner_email,
            'phone': self.partner_phone,
            'street1': payment_utils.format_partner_address(self.partner_address),
            'city': self.partner_city,
            'state': self.partner_state_id.name,
            'country': self.partner_country_id.code,
            'zip': self.partner_zip,
            'ip': payment_utils.get_customer_ip_address(),
        }
        payload = {
            'profile_id': self.provider_id.paytabs_profile_id,
            'tran_type': 'sale',
            'tran_class': 'ecom',
            'cart_id': self.reference,
            'cart_currency': self.currency_id.name,
            'cart_amount': self.amount,  # PayTabs expects amounts in major units.
            'cart_description': self.reference,
            # The payment page is only available in English and Arabic.
            'paypage_lang': 'ar' if (self.partner_lang or '').startswith('ar') else 'en',
            'customer_details': {k: v for k, v in customer_details.items() if v},
            'hide_shipping': self.provider_id.paytabs_hide_shipping,
            'return': urls.urljoin(return_base_url, PayTabsController._return_url),
            'callback': urls.urljoin(callback_base_url, PayTabsController._webhook_url),
        }
        # Restrict the payment page to the alternative payment method selected at checkout.
        paytabs_method_code = const.PAYMENT_METHODS_MAPPING.get(self.payment_method_code)
        if paytabs_method_code:
            payload['payment_methods'] = [paytabs_method_code]
        return payload

    def _send_refund_request(self):
        """ Override of `payment` to send a refund request to PayTabs. """
        if self.provider_code != 'paytabs':
            return super()._send_refund_request()

        payload = {
            'profile_id': self.provider_id.paytabs_profile_id,
            'tran_type': 'refund',
            'tran_class': 'ecom',
            'tran_ref': self.source_transaction_id.provider_reference,
            'cart_id': self.reference,
            'cart_currency': self.currency_id.name,
            'cart_amount': -self.amount,  # The amount is negative for refund transactions.
            'cart_description': _("Refund of %s", self.source_transaction_id.reference),
        }
        payment_data = self._send_api_request('POST', 'payment/request', json=payload)

        # PayTabs reports business errors with an HTTP 200 status and no payment result.
        if not payment_data.get('payment_result'):
            raise ValidationError("PayTabs: " + _(
                "The refund request was rejected. Reason: %(message)s (code %(code)s)",
                message=payment_data.get('message'),
                code=payment_data.get('code'),
            ))

        # The refund is assigned its own transaction reference on PayTabs' side.
        self.provider_reference = payment_data.get('tran_ref')
        self._process('paytabs', payment_data)

    # === BUSINESS METHODS - PROCESSING === #

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """ Override of `payment` to extract the reference from the payment data. """
        if provider_code != 'paytabs':
            return super()._extract_reference(provider_code, payment_data)
        # The key is snake_cased on webhook notifications and camelCased on redirect data.
        return payment_data.get('cart_id') or payment_data.get('cartId')

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to extract the amount and currency from the payment data. """
        if self.provider_code != 'paytabs':
            return super()._extract_amount_data(payment_data)

        # The amount and currency are not sent with the redirect data, only with webhook data.
        amount = payment_data.get('cart_amount')
        currency_code = payment_data.get('cart_currency')
        if amount is None or not currency_code:
            return None

        return {
            'amount': float(amount),  # PayTabs sends amounts in major units.
            'currency_code': currency_code,
        }

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction based on the payment data. """
        if self.provider_code != 'paytabs':
            return super()._apply_updates(payment_data)

        # Ensure that the transaction type matches the operation. Redirect data doesn't carry the
        # transaction type, in which case the check is skipped. As PayTabs may report a generic
        # transaction type for follow-ups, refund data is also matched on `previous_tran_ref`, which
        # references the source transaction.
        tran_type = payment_data.get('tran_type')
        if tran_type:
            tran_type = tran_type.lower()
            if self.operation == 'refund':
                previous_tran_ref = payment_data.get('previous_tran_ref')
                mismatch = tran_type != 'refund' and not (
                    previous_tran_ref
                    and previous_tran_ref == self.source_transaction_id.provider_reference
                )
            else:
                mismatch = tran_type in const.FOLLOW_UP_TRAN_TYPES

            if mismatch:
                _logger.warning(
                    "Ignored data for transaction %s with operation %s and transaction type %s.",
                    self.reference, self.operation, tran_type,
                )
                return

        # Update the provider reference.
        provider_reference = payment_data.get('tran_ref') or payment_data.get('tranRef')
        if provider_reference:
            self.provider_reference = provider_reference

        # Update the payment state.
        payment_result = payment_data.get('payment_result', {})
        payment_status = payment_result.get('response_status') or payment_data.get('respStatus')
        if not payment_status:
            self._set_error(_("Received data with missing payment status."))
            return

        if payment_status in const.PAYMENT_STATUS_MAPPING['pending']:
            self._set_pending()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['cancel']:
            self._set_canceled()
        elif payment_status in const.PAYMENT_STATUS_MAPPING['error']:
            response_code = payment_result.get('response_code') or payment_data.get('respCode')
            response_message = (
                payment_result.get('response_message') or payment_data.get('respMessage')
            )
            _logger.warning(
                "The transaction %s underwent an error. Reason: %s (%s)",
                self.reference, response_message, response_code,
            )
            # Keep the customer-facing message generic; the gateway's reason goes to the chatter.
            self._set_error(_(
                "An error occurred during the processing of your payment. Please try again."
            ))
            self._paytabs_log_decline_reason(payment_status, response_code, response_message)
        elif payment_status == const.ON_HOLD_STATUS:
            _logger.warning(
                "The transaction %s was authorized but put on hold by PayTabs.", self.reference
            )
            self._set_error(_(
                "Your payment could not be completed. Please contact us or try again."
            ))
            self._log_message_on_linked_documents(_(
                "PayTabs authorized the transaction %(ref)s but put the amount on hold (status H). "
                "Manual capture is not supported; capture or void it from the PayTabs dashboard.",
                ref=self._get_html_link(),
            ))
        else:  # Classify unsupported payment status as the `error` tx state.
            _logger.warning(
                "Received data for transaction %s with invalid payment status: %s.",
                self.reference, payment_status,
            )
            self._set_error(_("Received data with invalid status: %s.", payment_status))

        # Immediately post-process the transaction if it is a refund, as the post-processing will
        # not be triggered by a customer browsing the transaction from the portal.
        if self.operation == 'refund':
            self.env.ref('payment.cron_post_process_payment_tx')._trigger()

    def _paytabs_log_decline_reason(self, payment_status, response_code, response_message):
        """ Log PayTabs' decline reason on the documents linked to the transaction.

        The chatter is only visible to internal users, so the raw gateway reason can be logged
        there for the merchant while the customer keeps seeing the generic error message.

        :param str payment_status: The PayTabs response status (e.g. 'D' for declined).
        :param str response_code: The PayTabs response code, if any.
        :param str response_message: The PayTabs response message, if any.
        :return: None
        """
        self.ensure_one()
        status_labels = {
            'D': _("declined"),
            'E': _("failed"),
            'X': _("expired"),
        }
        reason = response_message or _("No reason provided")
        if response_code:
            reason = f'{reason} ({response_code})'
        message = _(
            "PayTabs reported the %(tx_label)s %(ref)s as %(status)s. Reason: %(reason)s",
            tx_label=_("refund") if self.operation == 'refund' else _("transaction"),
            ref=self._get_html_link(),
            status=status_labels.get(payment_status, payment_status),
            reason=reason,
        )
        self._log_message_on_linked_documents(message)
