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

from openerp import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.one
    @api.model
    def _catch_default_type(self):
        purchase_type = self.env.ref('purchase_order_type.seq_purchase_others')
        if not purchase_type:
            raise Warning(_('Purchase Type ERROR'),
                          _('OTHERS purchase type NOT FOUND'))
        return purchase_type.id

    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    project2_id = fields.Many2one('project.project', string='Subsubproject')
    project3_id = fields.Many2one('project.project', string='Project')
    type_cost = fields.Char('Type Cost', size=64)
    type = fields.Many2one('purchase.type', 'Type',
                           default=_catch_default_type)

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
