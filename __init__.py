# Copyright (C) PayTabs. Licensed under LGPL-3; see the LICENSE file for details.

from . import controllers
from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider


def post_init_hook(env):
    setup_provider(env, 'paytabs')


def uninstall_hook(env):
    reset_payment_provider(env, 'paytabs')
