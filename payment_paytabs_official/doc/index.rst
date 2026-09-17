==========================
Payment Provider: PayTabs
==========================

Official Odoo payment provider module for PayTabs.

Requirements
============

- Odoo **19.0**
- The ``payment`` module (installed automatically as a dependency)
- A PayTabs merchant account with a **Profile ID** and a **Server Key**

.. note::
   Remove any previous or third-party PayTabs module before installing this one.

Installation
============

#. Download the latest release of the module.
#. Copy the folder ``payment_paytabs_official`` into one of the directories listed in the ``addons_path``
   of your Odoo configuration file (e.g. ``/mnt/extra-addons/``).
#. Restart the Odoo server.
#. Go to *Apps*, click *Update Apps List* (developer mode must be active).
#. Search for ``PayTabs`` and click *Activate*.

Or from the command line::

    odoo -c /etc/odoo/odoo.conf -d <database> -i payment_paytabs_official --stop-after-init

Configuration
=============

#. Go to *Invoicing (or Website / Sales) » Configuration » Payment Providers*.
#. Open *PayTabs*.
#. Fill in the **Credentials** tab:

   - **Endpoint**: the PayTabs platform your profile was issued on. It selects the API host
     (``secure.paytabs.com``, ``secure.paytabs.sa``, ``secure-egypt.paytabs.com``, ...); a profile
     only authenticates against its own endpoint.
   - **Profile ID**: *Merchant's Dashboard » Developers » Key management » Profile ID*.
   - **Server Key**: *Merchant's Dashboard » Developers » Key management » Server Key*.

#. Set the **State**:

   - **Test Mode** when using a test profile.
   - **Enabled** when using a live profile.

   Test and live profiles share the same endpoint; only the Profile ID and Server Key differ.

#. Optionally, in the **Configuration** tab:

   - **Hide Shipping Details**: hide the shipping address section on the PayTabs payment page.
   - **Card Method Label**: the title shown at checkout for the **Card** method under PayTabs,
     e.g. ``PayTabs Payments``. Leave empty to keep the standard ``Card`` title.
   - **Payment Methods**: the methods listed here are shown with their icons at checkout. Only
     **Card** (Visa, Mastercard, American Express, Maestro, JCB, Diners, Discover, UnionPay,
     RuPay, Dankort, Meeza and OmanNet brands) is enabled by default; enable the others your
     PayTabs profile supports (Mada, STC Pay, Samsung Pay, Google Pay, KNET, Benefit, Tabby,
     Tamara, ValU, Aman, Forsa, Halan, Souhoola, Bank Installments, Contact, PayPal).

     When the customer selects an alternative payment method in Odoo, the PayTabs payment page is
     restricted to that method. When **Card**, **Benefit** or **Contact** is selected, the page
     offers every method enabled on your profile. Enable a method in Odoo only if it is also enabled on your PayTabs
     profile, otherwise PayTabs rejects the payment request.
   - **Capture Amount Manually**: authorize the amount at checkout and capture it later (see
     `Manual Capture`_). Odoo only allows it when every enabled payment method supports it
     (**Card**, **PayPal**, **Samsung Pay**, **Google Pay**); disable the other methods first.

#. Click *Save*, then publish the provider so that customers can see it at checkout.

Callback
========

The transaction is updated **only** from the server-to-server callback that PayTabs sends to::

    https://<your-odoo-domain>/payment/paytabs/webhook

The module passes this URL as the ``callback`` of every payment request; nothing has to be
configured in the PayTabs dashboard for it. The URL must be reachable from the internet over
**HTTPS**, and ``web.base.url`` must point to your public domain.

When the customer returns to Odoo (``/payment/paytabs/return``), the module only logs the result
and redirects to the payment status page; the outcome is displayed once the callback has been
processed.

.. note::
   The callback is not the IPN. The IPN is configured per profile in the merchant dashboard and
   reports changes to any transaction of the profile, including those made from the dashboard.
   The module does not rely on it; if you configure one, you may point it at the same webhook URL
   (duplicate notifications are handled), but follow-up transactions made from the dashboard
   (captures, voids, refunds) are ignored in this version.

Refunds
=======

#. Open the payment transaction (*Invoicing » Configuration » Payment Transactions*, or from the
   invoice's **Payments** smart button).
#. Click *Refund*, enter the amount (full or partial) and confirm.
#. The refund is sent to PayTabs; its status is updated from the callback.

Manual Capture
==============

With **Capture Amount Manually** enabled, the payment page authorizes the amount instead of
charging it, and the transaction is set to **Authorized** once the callback is processed.

#. Open the payment transaction (*Invoicing » Configuration » Payment Transactions*, or from the
   sales order's **Transactions** smart button).
#. Click *Capture* to charge the customer, or *Void* to release the authorized amount.
#. For a partial capture or void, enter the amount and confirm; the source transaction stays
   **Authorized** until the full amount has been captured or voided.

Captures and voids are sent to PayTabs immediately and their result is applied from the
response. The authorization holds the amount for a limited time, set by the card issuer; capture
it before it expires.

.. note::
   PayTabs may put a follow-up on hold (status ``H``) according to the profile's fraud rules. The
   transaction is then set in error in Odoo with the reason in the chatter; release or capture the
   amount from the PayTabs dashboard, as the API refuses further follow-ups on that transaction.

Transaction Statuses
====================

==================================================== ==========================================================================
PayTabs status                                       Odoo transaction state
==================================================== ==========================================================================
``A`` Authorised (``sale``, ``capture``, ``refund``) Done
``A`` Authorised (``auth``)                          Authorized
``A`` Authorised (``void``)                          Cancelled
``P`` Pending                                        Pending
``C`` Cancelled, ``V`` Voided                        Cancelled
``D`` Declined, ``E`` Error, ``X`` Expired           Error
``H`` Hold                                           Error — the amount is held; capture or release it from the PayTabs dashboard
==================================================== ==========================================================================

For declined, failed, expired and held transactions, the reason reported by PayTabs is posted in
the chatter of the linked invoice, sales order or payment for the merchant. The customer only sees
a generic message.

Not Implemented
===============

- Tokenization (saved cards)
- Express checkout
- IPN (follow-ups made from the PayTabs dashboard are not synchronized)

Testing From a Local Instance
=============================

PayTabs rejects payment requests whose callback URL is not publicly reachable. To test from a
local instance:

#. Expose it through a tunnel (e.g. ngrok, Cloudflare Tunnel).
#. Set the provider's **State** to **Test Mode**.
#. In the provider's **Configuration** tab, under **PayTabs: Tunnel (Test Mode)**, set **URL** to
   the tunnel address, e.g. ``https://xxxx.ngrok-free.app``.
#. Leave **Tunnel Callback** on (the webhook must be publicly reachable).
#. Leave **Tunnel Return** off unless the browser cannot reach the instance directly.

``web.base.url`` is left untouched. The tunnel section is only shown, and the tunnel URL only
used, while the provider is in test mode; switching to **Enabled** falls back to the system base
URL.

Test cards: https://support.paytabs.com/en/support/solutions/articles/60000709774

Logs
====

All requests, responses and notifications are written to the Odoo server log under the
``odoo.addons.payment_paytabs_official`` logger, with the server key and signatures masked.

Technical Details
=================

API: `PayTabs PT2 API <https://support.paytabs.com/en/support/solutions/folders/60000479499>`_

The module uses the generic payment-with-redirection flow of the ``payment`` module. The payment
page is created through the ``payment/request`` endpoint, which returns the URL the customer is
redirected to, with the ``sale`` transaction type, or ``auth`` when the amount is captured
manually. Refunds, captures and voids use the same endpoint with the ``refund``, ``capture`` and
``void`` transaction types, referencing the original transaction.

Callback notifications are signed with the server key (HMAC-SHA256 over the raw body, compared
with the ``signature`` header) and rejected if the signature does not match.

Support
=======

- Website: https://www.paytabs.com
- Email: customercare@paytabs.com

Changelog
=========

19.0.1.0.0
----------

- First release: hosted payment page, callback processing, refunds, manual capture and void.
