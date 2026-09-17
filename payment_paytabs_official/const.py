# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

from odoo.addons.payment.const import SENSITIVE_KEYS as PAYMENT_SENSITIVE_KEYS

# The supported PayTabs endpoints, mapped to their display label and API base URL. Several
# endpoints can serve the same country, so the selection is a platform, not a location.
# Test and live profiles share the same endpoint; only the profile ID differs. A profile only
# authenticates against the host it was issued for.
ENDPOINTS = {
    'ARE': ("United Arab Emirates", 'https://secure.paytabs.com'),
    'SAU': ("Saudi Arabia", 'https://secure.paytabs.sa'),
    'EGY': ("Egypt", 'https://secure-egypt.paytabs.com'),
    'OMN': ("Oman", 'https://secure-oman.paytabs.com'),
    'JOR': ("Jordan", 'https://secure-jordan.paytabs.com'),
    'KWT': ("Kuwait", 'https://secure-kuwait.paytabs.com'),
    'QAT': ("Qatar", 'https://secure-doha.paytabs.com'),
    'IRQ': ("Iraq", 'https://secure-iraq.paytabs.com'),
    'MAR': ("Morocco", 'https://secure-morocco.paytabs.com'),
    'GLOBAL': ("Global", 'https://secure-global.paytabs.com'),
    'MADFOAT': ("Madfoat", 'https://madfoat-secure.paytabs.com'),
    'CUZDAN': ("Cuzdan", 'https://secure.cuzdan.az'),
}

# The selection values of the `paytabs_endpoint` field.
ENDPOINT_SELECTION = [(code, label) for code, (label, _url) in ENDPOINTS.items()]

# The base URL of the PayTabs API for each supported endpoint.
API_URLS = {code: url for code, (_label, url) in ENDPOINTS.items()}

# The transaction types of follow-up operations performed against a prior transaction.
FOLLOW_UP_TRAN_TYPES = ('refund', 'void', 'release', 'capture')

# The transaction type of an authorization whose amount is captured later.
AUTH_TRAN_TYPE = 'auth'

# The transaction types PayTabs reports for the release of an authorized amount.
VOID_TRAN_TYPES = ('void', 'release')

# The codes of the payment methods to activate when PayTabs is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    # Primary payment methods.
    'card',
    # Brand payment methods.
    'visa',
    'mastercard',
    'amex',
    'maestro',
    'jcb',
    'diners',
    'discover',
    'unionpay',
    'rupay',
    'dankort',
    'meeza',
    'omannet',
}

# Mapping of payment method codes to PayTabs codes, for the `payment_methods` request parameter.
# Only alternative payment methods are mapped; card payments leave the payment page unrestricted so
# that every card scheme enabled on the profile is offered.
PAYMENT_METHODS_MAPPING = {
    'aman': 'aman',
    'forsa': 'forsa',
    'google_pay': 'google',
    'halan': 'halan',
    'installments_eg': 'installment',
    'knet': 'knet',
    'mada': 'mada',
    'paypal': 'paypal',
    'samsung_pay': 'samsungpay',
    'souhoola': 'souhoola',
    'stcpay': 'stcpay',
    'tabby': 'tabby',
    'tamara': 'tamara',
    'valu': 'valu',
}

# Mapping of transaction states to PayTabs' response statuses.
# See https://support.paytabs.com/en/support/solutions/articles/60000711358.
PAYMENT_STATUS_MAPPING = {
    'pending': ('P',),  # Awaiting an offline payment or a refund settlement.
    'done': ('A',),
    'cancel': ('C', 'V'),
    'error': ('D', 'E', 'X'),
}

# The status of a transaction that was authorized but whose amount is held by risk screening.
# PayTabs refuses API follow-ups on a held transaction until the merchant clears the hold from the
# dashboard, so the transaction cannot be captured or voided from Odoo.
ON_HOLD_STATUS = 'H'

# The keys of the payment data whose values must not be logged.
SENSITIVE_KEYS = {'signature', 'profile_id', 'server-key', 'token'}
PAYMENT_SENSITIVE_KEYS.update(SENSITIVE_KEYS)  # Add PayTabs-specific keys to the global set.
