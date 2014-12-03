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

from openerp.osv import fields, orm
from openerp.tools.translate import _
import time


class SimulationSelectTemplate(orm.TransientModel):
    _name = 'simulation.select.template'
    _description = "Wizard Select Template"

    _columns = {
        'template_id': fields.many2one('simulation.template', 'Template'),
    }

    def view_init(self, cr, uid, ids, context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simu_id = context.get('active_id')
        simulation_cost = simulation_cost_obj.browse(cr, uid, simu_id,
                                                     context=context)
        if simulation_cost.historical_date:
            raise orm.except_orm(_('Error'),
                                 _('This cost simulation have Historical'))

    def template_selected(self, cr, uid, ids, context=None):
        cost_line_obj = self.pool['simulation.cost.line']
        product_obj = self.pool['product.product']
        supplierinfo_obj = self.pool['product.supplierinfo']
        partner_obj = self.pool['res.partner']
        pricelist_obj = self.pool['product.pricelist']
        simu_id = context.get('active_id')
        for wiz in self.browse(cr, uid, ids, context):
            src_temp = wiz.template_id
            data = {}
            for line1 in src_temp.others_template_lines_ids:
                product = product_obj.browse(cr, uid, line1.product_id.id,
                                             context=context)
                # Cojo el primer proveedor para el producto
                condition = [('product_tmpl_id', '=',
                              line1.product_id.product_tmpl_id.id)]
                supplierinfo_ids = supplierinfo_obj.search(
                    cr, uid, condition, order='sequence', context=context)
                # Si no tiene cantidad, le pongo 1
                if not line1.amount:
                    line1.amount = 1.0
                # Diferencio si el producto tiene proveedores o no tiene
                if supplierinfo_ids:
                    supplierinfo_id = supplierinfo_obj.browse(
                        cr, uid, supplierinfo_ids[0], context=context)
                    supplier = partner_obj.browse(
                        cr, uid, supplierinfo_id.name.id, context=context)
                    lang = partner_obj.browse(
                        cr, uid, supplierinfo_id.name.id, context).lang
                    prlist = supplier.property_product_pricelist_purchase
                    pricelist_id = prlist.id
                    # Accedo a datos del producto.
                    context_partner = {
                        'lang': lang,
                        'partner_id': supplierinfo_id.name.id}
                    product = product_obj.browse(cr, uid, line1.product_id.id,
                                                 context=context_partner)
                    # Le pongo la fecha del sistema
                    purchase_completion_date = time.strftime('%Y-%m-%d')
                    # Cojo el precio de compra según tablas.
                    price = pricelist_obj.price_get(
                        cr, uid, [pricelist_id], product.id, line1.amount,
                        supplierinfo_id.name.id,
                        {'uom': product.uom_id.id,
                         'date': purchase_completion_date})[pricelist_id]
                    # Calculo el total compra
                    subtotal_purchase = line1.amount * price
                    # Calculo el margen estimado
                    if line1.product_id.list_price > 0 and price > 0:
                        estimated_margin = (line1.product_id.list_price /
                                            price)-1
                    else:
                        estimated_margin = 0
                    pdate = purchase_completion_date
                    data = {
                        'simulation_cost_id': simu_id,
                        'product_id': line1.product_id.id,
                        'product_sale_id': line1.product_id.id,
                        'name': line1.name,
                        'description': line1.description,
                        'supplier_id': supplierinfo_id.name.id,
                        'purchase_price': price,
                        'sale_price': line1.product_id.list_price,
                        'uom_id': line1.uom_id.id,
                        'amount': line1.amount,
                        'subtotal_purchase': subtotal_purchase,
                        'amortization_rate': 0,
                        'amortization_cost': 0,
                        'indirect_cost_rate': 0,
                        'indirect_cost': 0,
                        'type_cost': line1.type_cost,
                        'type2': line1.type2,
                        'type3': line1.type3,
                        'template_id': src_temp.id,
                        'estimated_date_purchase_completion': pdate,
                        'estimated_margin': estimated_margin
                    }
                    cost_line_obj.create(cr, uid, data, context)
                else:
                    # Calculo el total de la venta
                    if product.standard_price:
                        subtotal_purchase = (line1.amount *
                                             product.standard_price)
                    else:
                        subtotal_purchase = 0
                    # Calculo el margen estimado
                    if (line1.product_id.list_price > 0 and
                            product.standard_price > 0):
                        estimated_margin = (line1.product_id.list_price /
                                            product.standard_price)-1
                    else:
                        estimated_margin = 0
                    data = {'simulation_cost_id': simu_id,
                            'product_id': line1.product_id.id,
                            'product_sale_id': line1.product_id.id,
                            'name': line1.name,
                            'description': line1.description,
                            'purchase_price': product.standard_price,
                            'sale_price': line1.product_id.list_price,
                            'amortization_rate': 0,
                            'amortization_cost': 0,
                            'indirect_cost_rate': 0,
                            'indirect_cost': 0,
                            'uom_id': line1.uom_id.id,
                            'amount': line1.amount,
                            'subtotal_purchase': subtotal_purchase,
                            'type_cost': line1.type_cost,
                            'type2': line1.type2,
                            'type3': line1.type3,
                            'template_id': src_temp.id,
                            'estimated_margin': estimated_margin
                            }
                    cost_line_obj.create(cr, uid, data, context)
        return {'type': 'ir.actions.act_window_close'}
