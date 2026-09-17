# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

{
    'name': "Payment Provider: PayTabs",
    'version': '19.0.2.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider covering the Middle East and North Africa.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'images': ['static/description/paytabs-strapline.png'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_paytabs_official_templates.xml',

        'data/payment_provider_data.xml',  # Depends on views/payment_paytabs_official_templates.xml
        'data/payment_method_data.xml',  # Depends on data/payment_provider_data.xml
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'author': "PayTabs",
    'maintainer': "PayTabs",
    'website': "https://www.paytabs.com",
    'support': "customercare@paytabs.com",
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
