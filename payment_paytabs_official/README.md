# PayTabs - Odoo

Official Odoo payment provider module for PayTabs

---

## Requirements

- Odoo **19.0**
- The `payment` module (installed automatically as a dependency)
- A PayTabs merchant account with a **Profile ID** and a **Server Key**

*Note: Remove any previous or third-party PayTabs module before installing this one.*

---

## Installation

1. Download the latest release of the module
2. Copy the folder `payment_paytabs_official` into one of the directories listed in the `addons_path` of
   your Odoo configuration file (e.g. `/mnt/extra-addons/`)
3. Restart the Odoo server
4. Go to `Odoo >> Apps`, click `Update Apps List` (developer mode must be active)
5. Search for `PayTabs` and click `Activate`

Or from the command line:

```bash
odoo -c /etc/odoo/odoo.conf -d <database> -i payment_paytabs_official --stop-after-init
```

---

## Configure the Module

1. Go to `Odoo >> Invoicing (or Website / Sales) >> Configuration >> Payment Providers`
2. Open `PayTabs`
3. Fill in the **Credentials** tab:
   - **Region**: the region your PayTabs account was issued for. It selects the API endpoint
     (`secure.paytabs.com`, `secure.paytabs.sa`, `secure-egypt.paytabs.com`, ...); a profile only
     authenticates against its own region
   - **Profile ID**: `Merchant’s Dashboard >> Developers >> Key management >> Profile ID`
   - **Server Key**: `Merchant’s Dashboard >> Developers >> Key management >> Server Key`
4. Set the **State**:
   - **Test Mode** when using a test profile
   - **Enabled** when using a live profile

   *Note: Test and live profiles share the same endpoint; only the Profile ID and Server Key
   differ.*
5. Optionally, in the **Configuration** tab:
   - **Hide Shipping Details**: hide the shipping address section on the PayTabs payment page
   - **Card Method Label**: the title shown at checkout for the **Card** method under PayTabs, e.g.
     `PayTabs Payments`. Leave empty to keep the standard `Card` title; other providers and
     payment methods are not affected
   - **Payment Methods**: the methods listed here are shown with their icons at checkout. Only
     **Card** (Visa, Mastercard, American Express, Maestro, JCB, Diners, Discover, UnionPay,
     RuPay, Dankort, Meeza and OmanNet brands) is enabled by default; enable the others your
     PayTabs profile supports from the list (Mada, STC Pay, Samsung Pay, Google Pay, KNET, Benefit,
     Tabby, Tamara, ValU, Aman, Forsa, Halan, Souhoola, Bank Installments, Contact, PayPal).

   *Note: when the customer selects an alternative payment method (Mada, STC Pay, ...) in Odoo,
   the PayTabs payment page is restricted to that method (`payment_methods` parameter). When
   **Card**, **Benefit** or **Contact** is selected, the page offers every method enabled on your
   profile. Enable a method in Odoo only if it is also enabled on your PayTabs profile, otherwise
   PayTabs rejects the payment request.*
   - **Capture Amount Manually**: authorize the amount at checkout and capture it later (see
     [Use Manual Capture](#use-manual-capture)). Odoo only allows it when every enabled payment
     method supports it (**Card**, **PayPal**, **Samsung Pay**, **Google Pay**); disable the other
     methods first
6. Click `Save`

---

## Callback

The transaction is updated **only** from the server-to-server callback that PayTabs sends to:

```
https://<your-odoo-domain>/payment/paytabs/webhook
```

The module passes this URL as the `callback` of every payment request; nothing has to be configured
in the PayTabs dashboard for it. The URL must be reachable from the internet over **HTTPS**, and
`web.base.url` must point to your public domain.

When the customer returns to Odoo (`/payment/paytabs/return`), the module only logs the result and
redirects to the payment status page; the outcome is displayed once the callback has been
processed.

*Note: The callback is not the IPN. The IPN is configured per profile in the merchant dashboard and
reports changes to any transaction of the profile, including those made from the dashboard. The module does not rely on it; if you configure one, you
may point it at the same webhook URL — duplicate notifications are handled — but follow-up
transactions made from the dashboard (captures, voids, refunds) are ignored in this version.*

---

## Use Refunds

1. Open the payment transaction (`Invoicing >> Configuration >> Payment Transactions`, or from the
   invoice's **Payments** smart button)
2. Click `Refund`, enter the amount (full or partial) and confirm
3. The refund is sent to PayTabs; its status is updated from the callback

---

## Use Manual Capture

With **Capture Amount Manually** enabled, the payment page authorizes the amount instead of
charging it, and the transaction is set to **Authorized** once the callback is processed.

1. Open the payment transaction (`Invoicing >> Configuration >> Payment Transactions`, or from the
   sales order's **Transactions** smart button)
2. Click `Capture` to charge the customer, or `Void` to release the authorized amount
3. For a partial capture or void, enter the amount and confirm; the source transaction stays
   **Authorized** until the full amount has been captured or voided

Captures and voids are sent to PayTabs immediately and their result is applied from the response.
The authorization holds the amount for a limited time, set by the card issuer; capture it before
it expires.

*Note: PayTabs may put a follow-up on hold (status `H`) according to the profile's fraud rules.
The transaction is then set in error in Odoo with the reason in the chatter; release or capture the
amount from the PayTabs dashboard, as the API refuses further follow-ups on that transaction.*

---

## Transaction Statuses

| PayTabs status | Odoo transaction state |
| --- | --- |
| `A` Authorised (`sale`, `capture`, `refund`) | Done |
| `A` Authorised (`auth`) | Authorized |
| `A` Authorised (`void`) | Cancelled |
| `P` Pending | Pending |
| `C` Cancelled, `V` Voided | Cancelled |
| `D` Declined, `E` Error, `X` Expired | Error |
| `H` Hold | Error — the amount is held; capture or release it from the PayTabs dashboard |

For declined, failed, expired and held transactions, the reason reported by PayTabs is posted in the
chatter of the linked invoice, sales order or payment for the merchant. The customer only sees a
generic message.

---

## Not Implemented

- Tokenization (saved cards)
- Express checkout
- IPN (follow-ups made from the PayTabs dashboard are not synchronized)

---

## Development: Test From a Local Instance

PayTabs rejects payment requests whose callback URL is not publicly reachable. To test from a
local instance:

1. Expose it through a tunnel (e.g. [ngrok](https://ngrok.com), Cloudflare Tunnel)
2. Set the provider's **State** to **Test Mode**
3. In the provider's **Configuration** tab, under **PayTabs: Tunnel (Test Mode)**, set **URL**
   to the tunnel address, e.g. `https://xxxx.ngrok-free.app`
4. Leave **Tunnel Callback** on (the webhook must be publicly reachable)
5. Leave **Tunnel Return** off unless the browser cannot reach the instance directly

`web.base.url` is left untouched. The tunnel section is only shown, and the tunnel URL only
used, while the provider is in test mode; switching to **Enabled** falls back to the system base
URL.

Test cards: https://support.paytabs.com/en/support/solutions/articles/60000709774

---

## Log Access

All requests, responses and notifications are written to the Odoo server log under the
`odoo.addons.payment_paytabs_official` logger, with the server key and signatures masked. Check the file
set by `logfile` in your Odoo configuration, or the container/stdout logs.

---

## Technical Details

API: [PayTabs PT2 API](https://support.paytabs.com/en/support/solutions/folders/60000479499)

The module uses the generic payment-with-redirection flow of the `payment` module. The payment
page is created through the `payment/request` endpoint, which returns the URL the customer is
redirected to, with the `sale` transaction type, or `auth` when the amount is captured manually.
Refunds, captures and voids use the same endpoint with the `refund`, `capture` and `void`
transaction types, referencing the original transaction. PayTabs accepts `void` for both the full
and the partial release of an authorized amount.

Callback notifications are signed with the server key (HMAC-SHA256 over the raw body, compared
with the `signature` header) and rejected if the signature does not match.

---

## Module History

- `19.0.1.0.0`
  - The first version of the module is released: hosted payment page, callback processing,
    refunds, manual capture and void.
