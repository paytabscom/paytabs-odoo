# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

import hmac
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_paytabs_official import const


_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class PayTabsController(http.Controller):
    _return_url = '/payment/paytabs/return'
    _webhook_url = '/payment/paytabs/webhook'

    @http.route(
        _return_url,
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        save_session=False,
    )
    def paytabs_return_from_checkout(self, **data):
        """ Redirect the customer to the status page after returning from PayTabs' checkout.

        This route never updates the transaction: the webhook route is the single channel through
        which the transaction is processed. The redirect data is only logged for support purposes;
        the customer is then sent to the status page, which displays the outcome once the webhook
        notification has been processed and redirects to the thank-you or order page.

        PayTabs POSTs the payment result to HTTPS return URLs only. When the return URL is plain
        HTTP, the customer is redirected with a bare GET request instead; the route accepts both.

        The route is configured with save_session=False to prevent Odoo from creating a new session
        when the user is redirected here via a POST request. Indeed, as the session cookie is
        created without a `SameSite` attribute, some browsers that don't implement the recommended
        default `SameSite=Lax` behavior will not include the cookie in the redirection request from
        the payment provider to Odoo. However, the redirection to the /payment/status page will
        satisfy any specification of the `SameSite` attribute, the session of the user will be
        retrieved and with it the transaction which will be immediately post-processed.

        :param dict data: The payment data, if any.
        """
        _logger.info("Handling redirection from PayTabs with data:\n%s", pprint.pformat(data))
        payment_status = data.get('respStatus')
        if payment_status:
            _logger.info(
                "Customer returned from PayTabs for transaction %s with payment result %s (%s).",
                data.get('cartId'), payment_status, data.get('respMessage'),
            )

        # Redirect the user to the status page.
        return request.redirect('/payment/status')

    @http.route(
        _webhook_url,
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def paytabs_webhook(self):
        """ Process the payment data sent by PayTabs to the webhook. """
        try:
            data = request.get_json_data()
        except ValueError:
            _logger.warning("Received a notification with a malformed body.")
            raise Forbidden()
        _logger.info("Callback received from PayTabs with data:\n%s", pprint.pformat(data))

        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('paytabs', data)
        if tx_sudo:
            received_signature = request.httprequest.headers.get('signature')
            self._verify_signature(
                request.httprequest.data, received_signature, tx_sudo, is_redirect=False
            )
            self._verify_profile(data, tx_sudo, required=True)
            tx_sudo._process('paytabs', data)

        return request.make_json_response('')  # Acknowledge the notification.

    @staticmethod
    def _verify_signature(payment_data, received_signature, tx_sudo, is_redirect=True):
        """ Check that the received signature matches the expected one.

        :param dict|bytes payment_data: The payment data.
        :param str received_signature: The signature to compare with the expected signature.
        :param payment.transaction tx_sudo: The sudoed transaction referenced by the payment data.
        :param bool is_redirect: Whether the payment data should be treated as redirect data or as
                                 coming from a webhook notification.
        :return: None
        :raise Forbidden: If the signatures don't match.
        """
        # Check for the received signature. The type must be asserted explicitly, as a repeated
        # field could otherwise surface as a non-empty list and bypass a mere truthiness check.
        if not isinstance(received_signature, str) or not received_signature:
            _logger.warning("Received payment data with missing signature.")
            raise Forbidden()

        # Compare the received signature with the expected signature. The digests are compared
        # case-insensitively, as the casing of hex digests is not guaranteed.
        expected_signature = tx_sudo.provider_id._paytabs_calculate_signature(
            payment_data, is_redirect=is_redirect
        )
        try:
            signatures_match = hmac.compare_digest(
                received_signature.lower(), expected_signature.lower()
            )
        except TypeError:  # `compare_digest` rejects non-ASCII strings.
            signatures_match = False
        if not signatures_match:
            _logger.warning("Received payment data with invalid signature.")
            raise Forbidden()

    @staticmethod
    def _verify_profile(payment_data, tx_sudo, required=False):
        """ Check that the payment data was signed for the profile of the transaction's provider.

        A valid signature only proves that the payment data was signed by some key, not that it was
        signed for this merchant account.

        :param dict payment_data: The payment data.
        :param payment.transaction tx_sudo: The sudoed transaction referenced by the payment data.
        :param bool required: Whether the profile ID must be present in the payment data. Webhook
                              notifications always carry it, redirect data might not.
        :return: None
        :raise Forbidden: If the profile IDs don't match, or if the profile ID is missing while
                          required.
        """
        profile_id = payment_data.get('profile_id') or payment_data.get('profileId')
        if not profile_id:
            if required:
                _logger.warning("Received payment data with missing profile ID.")
                raise Forbidden()
            return
        if str(profile_id) != str(tx_sudo.provider_id.paytabs_profile_id):
            _logger.warning("Received payment data for another PayTabs profile.")
            raise Forbidden()
