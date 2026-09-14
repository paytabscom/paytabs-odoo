# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

import hashlib
import hmac
from urllib.parse import quote_plus

from odoo import fields, models, release

from odoo.addons.payment_paytabs_official import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('paytabs', "PayTabs")], ondelete={'paytabs': 'set default'}
    )
    paytabs_region = fields.Selection(
        string="PayTabs Region",
        help="The region of the PayTabs account, which determines the API endpoint to use. It must"
             " match the region the profile was issued for, or PayTabs rejects the server key.",
        selection=const.REGION_SELECTION,
        default='ARE',
        required_if_provider='paytabs',
        copy=False,
    )
    paytabs_profile_id = fields.Integer(
        string="PayTabs Profile ID",
        help="The profile ID of the PayTabs account. Test and live accounts have distinct"
             " profile IDs.",
        required_if_provider='paytabs',
        copy=False,
    )
    paytabs_server_key = fields.Char(
        string="PayTabs Server Key",
        help="The server key of the PayTabs account, found under Developers > Key management.",
        required_if_provider='paytabs',
        copy=False,
        groups='base.group_system',
    )
    paytabs_hide_shipping = fields.Boolean(
        string="Hide Shipping Details",
        help="Whether to hide the shipping address section on the PayTabs payment page. Odoo"
             " never sends shipping details to PayTabs, so leave it enabled unless the payment"
             " page must collect them.",
        default=True,
    )
    paytabs_card_label = fields.Char(
        string="Card Method Label",
        help="The title shown at checkout for the Card payment method of this provider, e.g."
             " \"PayTabs Payments\". Leave empty to keep the standard \"Card\" title. Other"
             " payment methods keep their own name.",
        translate=True,
    )
    paytabs_tunnel_url = fields.Char(
        string="Tunnel URL",
        help="The public HTTPS URL PayTabs must use to reach this instance when it is not exposed"
             " directly, e.g. through a development tunnel (ngrok, Cloudflare Tunnel) or a"
             " reverse proxy with a different hostname. Only the return and callback URLs sent to"
             " PayTabs are affected, and only while the provider is in test mode. Leave empty to"
             " use the system base URL.",
        copy=False,
    )
    paytabs_tunnel_callback = fields.Boolean(
        string="Tunnel Callback URL",
        help="Send the webhook (callback) notifications through the tunnel URL. PayTabs calls"
             " this URL server-to-server, so it must be publicly reachable.",
        default=True,
    )
    paytabs_tunnel_return = fields.Boolean(
        string="Tunnel Return URL",
        help="Redirect the customer back through the tunnel URL after payment. Usually left"
             " disabled: the customer's browser can already reach the instance directly, and"
             " the return page then keeps the session it started the payment with.",
        default=False,
    )

    # === COMPUTE METHODS === #

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'paytabs').update({
            'support_manual_capture': 'partial',
            'support_refund': 'partial',
        })

    # === BUSINESS METHODS === #

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        self.ensure_one()
        if self.code != 'paytabs':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _paytabs_calculate_signature(self, data, is_redirect=True):
        """ Compute the signature for the payment data according to the PayTabs documentation.

        Note: `self.ensure_one()`

        :param dict|bytes data: The payment data to sign. A dict of form fields for redirect data,
                                the raw request body for webhook notifications.
        :param bool is_redirect: Whether the data should be treated as redirect data or as coming
                                 from a webhook notification.
        :return: The calculated signature.
        :rtype: str
        """
        self.ensure_one()

        if is_redirect:
            # PayTabs signs the URL-encoded query string of the form fields, sorted by key, with
            # the signature field itself left out. Only null and empty values are dropped; a '0'
            # value is part of the signed payload and must be kept.
            signing_string = '&'.join(
                f'{quote_plus(k)}={quote_plus(str(v))}'
                for k, v in sorted(data.items())
                if k != 'signature' and v is not None and v != ''
            ).encode()
        else:
            signing_string = data
        return hmac.new(
            self.paytabs_server_key.encode(), msg=signing_string, digestmod=hashlib.sha256
        ).hexdigest()

    def _paytabs_get_public_base_url(self, url_type):
        """ Return the base URL to embed in the `return` or `callback` URL.

        PayTabs rejects payment requests whose callback URL is not publicly reachable, and only
        POSTs the signed return data to an HTTPS URL. When the provider is in test mode and the
        tunnel URL is set and enabled for the requested URL type, it overrides the instance base
        URL. A tunnel URL left over from development is ignored once the provider goes live.

        :param str url_type: Either 'return' or 'callback'.
        :return: The base URL, without a trailing slash.
        :rtype: str
        """
        self.ensure_one()
        use_tunnel = self.state == 'test' and {
            'return': self.paytabs_tunnel_return,
            'callback': self.paytabs_tunnel_callback,
        }[url_type]
        base_url = self.paytabs_tunnel_url if use_tunnel and self.paytabs_tunnel_url else None
        return (base_url or self.get_base_url()).strip().rstrip('/')

    def _paytabs_get_plugin_info(self):
        """ Return the `plugin_info` payload identifying the integration to PayTabs.

        :return: The plugin info with the platform name and version and the module version.
        :rtype: dict
        """
        return {
            'cart_name': 'odoo',  # Platform name registered on the PayTabs side; not free text.
            'cart_version': release.version,
            'plugin_version': self.env.ref('base.module_payment_paytabs_official').installed_version,
        }

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URL. """
        if self.code != 'paytabs':
            return super()._build_request_url(endpoint, **kwargs)
        base_url = const.API_URLS.get(self.paytabs_region)
        if not base_url:
            raise ValueError(f"Unknown PayTabs region: {self.paytabs_region!r}")
        return f'{base_url.rstrip("/")}/{endpoint.lstrip("/")}'

    def _build_request_headers(self, *args, **kwargs):
        """ Override of `payment` to include the server key in the headers. """
        if self.code != 'paytabs':
            return super()._build_request_headers(*args, **kwargs)
        return {'Authorization': self.paytabs_server_key}

    def _parse_response_error(self, response):
        """ Override of `payment` to extract the error message from the response. """
        if self.code != 'paytabs':
            return super()._parse_response_error(response)
        response_content = response.json()
        message = response_content.get('message', '')
        code = response_content.get('code')
        if code is not None:
            message = f'{message} (code {code})'
        return message
