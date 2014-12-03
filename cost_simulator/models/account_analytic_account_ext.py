# -*- encoding: utf-8 -*-
##############################################################################
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see http://www.gnu.org/licenses/.
#
##############################################################################

from openerp.osv import orm, fields
from openerp.addons import decimal_precision as dp


class AccountAnalyticAccountaccount(orm.Model):
    _inherit = 'account.analytic.account'

    def name_get(self, cr, uid, ids, context=None):
        if not ids:
            return []
        res = []
        for account in self.browse(cr, uid, ids, context=context):
            data = []
            acc = account
            if acc:
                data.insert(0, acc.name)
            data = ' / '.join(data)
            res.append((account.id, data))
        return res

    _columns = {
        # Balance en simulación
        'estimated_balance':
            fields.float('Estimated Balance', readonly=True,
                         digits_compute=dp.get_precision('Account')),
        # Precio de compra en simulación
        'estimated_cost':
            fields.float('Estimated Cost', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Precio de venta en simulación
        'estimated_sale':
            fields.float('Estimated Sale', readonly=True,
                         digits_compute=dp.get_precision('Sale Price')),
    }

    def button_analytical_structure_update_costs(self, cr, uid, ids, *args):
        return True
