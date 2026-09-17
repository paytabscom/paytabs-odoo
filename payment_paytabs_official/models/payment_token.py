# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    paytabs_tran_ref = fields.Char(
        string="PayTabs Transaction Reference",
        help="The reference of the transaction that created the token; PayTabs requires it to"
             " charge the token.",
        readonly=True,
    )

    def _handle_archiving(self):
        """ Override of `payment` to delete the token on PayTabs when it is archived.

        PayTabs tokens can only be revoked through the API; deleting them when they are archived
        in Odoo ensures they can no longer be charged. A failed deletion is logged but does not
        prevent archiving the token.
        """
        for token in self.filtered(lambda t: t.provider_code == 'paytabs'):
            payload = {
                'profile_id': token.provider_id.paytabs_profile_id,
                'token': token.provider_ref,
            }
            try:
                token.provider_id._send_api_request('POST', 'payment/token/delete', json=payload)
            except ValidationError as error:
                _logger.warning(
                    "Could not delete token %s on PayTabs: %s", token.id, error
                )
        return super()._handle_archiving()
