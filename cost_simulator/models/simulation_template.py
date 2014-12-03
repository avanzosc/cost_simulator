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


class SimulationTemplate(orm.Model):

    _name = 'simulation.template'
    _description = 'Simulation Template'

    _columns = {
        'name': fields.char('Name', size=64, required="True", select=1),
        # Producto de la plantilla
        'template_product_id': fields.many2one('product.product',
                                               'Product for sale'),
        'others_template_lines_ids':
            fields.one2many('simulation.template.line', 'template_id',
                            'Others Lines',
                            domain=[('type_cost', '=', 'Others')]),
    }


class SimulationTemplateLine(orm.Model):
    _name = 'simulation.template.line'
    _description = 'Simulation Template Line'

    _columns = {
        'template_id': fields.many2one('simulation.template', 'Template',
                                       ondelete='cascade'),
        'product_id': fields.many2one('product.product', 'Product',
                                      required=True),
        'name': fields.char('Name', size=64, required=True),
        'description': fields.text('Description'),
        'amortization_rate': fields.float('Amortization Rate', digits=(3, 2)),
        'indirect_cost_rate': fields.float('Indirect Cost Rate',
                                           digits=(3, 2)),
        'amount': fields.float('Amount',
                               digits_compute=dp.get_precision('Product UoM')),
        'uom_id': fields.many2one('product.uom', 'Default Unit Of Measure',
                                  required=True),
        'type_cost': fields.selection([('Others', 'Others')], 'Type of Cost'),
        'type2': fields.selection([('fixed', 'Fixed'),
                                   ('variable', 'Variable')],
                                  'Fixed/Variable'),
        'type3': fields.selection([('marketing', 'Marketing'),
                                   ('sale', 'Sale'),
                                   ('production', 'Production'),
                                   ('generalexpenses', 'General Expenses'),
                                   ('structureexpenses', 'Structure Expenses'),
                                   ('amortizationexpenses',
                                    'Amortization Expenses')],
                                  'Cost Category'),
    }
    _defaults = {
        'type_cost': lambda self, cr, uid, c: c.get('type_cost', False),
        'amount': 1.0,
    }

    def onchange_product(self, cr, uid, ids, product_id, type, context=None):
        product_obj = self.pool['product.product']
        if product_id and type:
            product = product_obj.browse(cr, uid, product_id, context=context)
            res = {'name': (product.name or ''),
                   'description': (product.description or ''),
                   'uom_id': product.uom_id.id,
                   'amortization_rate': product.amortization_rate,
                   'indirect_cost_rate': product.indirect_cost_rate,
                   }
            return {'value': res}

    def onchange_type_cost(self, cr, uid, ids, type, context=None):
        res = {'product_id': '',
               'name': '',
               'description': '',
               'uom_id': '',
               'amount': 0
               }
        return {'value': res}
