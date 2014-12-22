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
from openerp.tools.translate import _


class PurchaseOrder(orm.Model):
    _inherit = 'purchase.order'

    def _catch_default_type(self, cr, uid, context=None):
        if not context:
            context = {}
        purchase_type_obj = self.pool['purchase.type']
        purchase_type_ids = purchase_type_obj.search(
            cr, uid, [('name', '=', 'Others')], context=context)
        if purchase_type_ids:
            for purchase_type_id in purchase_type_ids:
                return purchase_type_id

    _columns = {
        # Campo para saber que pedidos de compra se han generado a partir del
        # pedido de venta
        'sale_order_id': fields.many2one('sale.order', 'Sale Order'),
        # Campo para relacionar los pedidos de compra con el subsubproyecto
        'project2_id': fields.many2one('project.project', 'Subsubproject'),
        # Campo para relacionar los pedidos de compra con el Projecto
        'project3_id': fields.many2one('project.project', 'Project'),
        # Campo para saber a que tipo de coste pertenece la orden de pedido
        # de compra
        'type_cost': fields.char('Type Cost', size=64),
        # Tipo de compra
        'type': fields.many2one('purchase.type', 'Type'),
    }

    _defaults = {
        'type': lambda self, cr, uid, c: self._catch_default_type(cr, uid,
                                                                  context=c),
    }

    def onchange_purchase_type(self, cr, uid, ids, type, context=None):
        purchase_type_obj = self.pool['purchase.type']
        sequence_obj = self.pool['ir.sequence']
        res = {}
        if type:
            purchase_type = purchase_type_obj.browse(cr, uid, type,
                                                     context=context)
            code = purchase_type.sequence.code
            seq = sequence_obj.get(cr, uid, code)
            res.update({'name': seq})
        return {'value': res}

    def wkf_confirm_order(self, cr, uid, ids, context=None):
        res = super(PurchaseOrder, self).wkf_confirm_order(cr, uid, ids,
                                                           context)
        return res
