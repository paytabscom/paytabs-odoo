# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: PayTabs",
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider covering the Middle East and North Africa.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_paytabs_templates.xml',

        'data/payment_provider_data.xml',  # Depends on views/payment_paytabs_templates.xml
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'author': "PayTabs",
    'website': "https://www.paytabs.com",
    'license': 'LGPL-3',
}
