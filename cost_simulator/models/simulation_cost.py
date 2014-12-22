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
from openerp.tools.translate import _
import time


class SimulationCost(orm.Model):

    _name = 'simulation.cost'
    _description = 'Simulation Costs'

    _columns = {
        'simulation_number': fields.char('Serial', size=64),
        'name': fields.char('Description/Name', size=250, required=True,
                            attrs={'readonly': [('historical_ok', '=',
                                                 True)]}),
        'partner_id': fields.many2one('res.partner', 'Customer'),
        'historical_date': fields.datetime('Historical Date', readonly=True),
        'historical_ok': fields.boolean('Historical OK'),
        'overhead_costs':
            fields.float('Overhead Costs',
                         digits_compute=dp.get_precision('Purchase Price')),
        'purchase_insale': fields.boolean('Copy Purchase information in Sale '
                                          'information'),
        'others_cost_lines_ids':
            fields.one2many('simulation.cost.line', 'simulation_cost_id',
                            'Others Lines',
                            domain=[('type_cost', '=', 'Others')],
                            attrs={'readonly': [('historical_ok', '=',
                                                 True)]}),
        # Total compras, ventas, beneficio para tipo coste others
        'subtotal5_purchase':
            fields.float('Total Purchase', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        'subtotal5_sale':
            fields.float('Total Sale', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        'benefit5':
            fields.float('Total Benefit', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Campos para los totales de la última pestaña
        'subtotal5t_purchase':
            fields.float('Total Purchase', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        'subtotal5t_sale':
            fields.float('Total Sale', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        'benefit5t':
            fields.float('Total Benefit', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total Costes
        'total_costs':
            fields.float('TOTAL COSTS', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total Ventas
        'total_sales':
            fields.float('TOTAL SALES', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total Beneficios
        'total_benefits':
            fields.float('TOTAL BENEFITS', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total amortizaciones
        'total_amortizations':
            fields.float('Total Amortizations', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total indirectos
        'total_indirects':
            fields.float('Total Indirects', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total amortizaciones + indirectos
        'total_amort_indirects':
            fields.float('TOTAL', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Gastos Generales
        'total_overhead_costs':
            fields.float('Overhead_costs', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Total
        'total':
            fields.float('TOTAL', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Precio Neto
        'net_cost':
            fields.float('Net Cost', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Porcentaje Precio Neto
        'net_cost_percentage': fields.float('Net Cost %', digits=(3, 2),
                                            readonly=True),
        # Margen Bruto
        'gross_margin':
            fields.float('Gross Margin', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Porcentaje Margen Bruto
        'gross_margin_percentage':
            fields.float('Gross Margin %', digits=(3, 2), readonly=True),
        # Margen de Contribución
        'contribution_margin':
            fields.float('Contribution Margin', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Porcentaje Margen Contribucion
        'contribution_margin_percentage':
            fields.float('Contribution Margin %', digits=(3, 2),
                         readonly=True),
        # Margen Neto
        'net_margin':
            fields.float('Net Margin', readonly=True,
                         digits_compute=dp.get_precision('Purchase Price')),
        # Porcentaje Margen Neto
        'net_margin_percentage': fields.float('Net Margin %', digits=(3, 2),
                                              readonly=True),
        # Pedidos de Venta
        'sale_order_ids':
            fields.many2many('sale.order', 'simucost_saleorder_rel',
                             'simulation_cost_id', 'sale_order_id',
                             'Sale Orders', readonly=True),
        # Proyectos
        'project_ids': fields.one2many('project.project', 'simulation_cost_id',
                                       'Projects'),
        # Subproyectos
        'subproject_ids':
            fields.one2many('project.project', 'simulation_cost_id2',
                            'Subprojects'),
        # Generar Pedido de venta por productos de lineas de simulacion
        'generate_by_line': fields.boolean('Generate by line'),
        # WORKFLOW DE LA SIMULACION DEL COSTE
        'state': fields.selection([('draft', 'Draft'),
                                   ('accepted', 'Accepted'),
                                   ('canceled', 'Canceled'),
                                   ], 'State', readonly=True)
    }

    _defaults = {'state': lambda *a: 'draft',
                 'historical_ok': lambda *a: False,
                 'purchase_insale': lambda *a: True
                 }

    def create(self, cr, uid, data, context=None):
        sequence_obj = self.pool['ir.sequence']
        seria = sequence_obj.get(cr, uid, 'cost.serial'),
        serial = seria[0]
        data.update({'simulation_number': serial})
        return super(SimulationCost, self).create(cr, uid, data, context)

    def unlink(self, cr, uid, ids, context=None):
        unlink_ids = []
        for simulation_cost in self.browse(cr, uid, ids, context=context):
            if simulation_cost.sale_order_ids:
                raise orm.except_orm(_('Invalid action !'),
                                     _('This Simulation Costs Have Associated '
                                       'Sales Orders'))
            unlink_ids.append(simulation_cost.id)
        orm.Model.unlink(self, cr, uid, unlink_ids, context=context)
        return True

    # BOTÓN RECALCULAR TOTALES, este boton está en todas las pestañas
    def button_recalculation(self, cr, uid, ids, *args):
        cost_line_obj = self.pool['simulation.cost.line']
        simulation_cost = self.browse(cr, uid, ids[0])
        # valido que no esté historificado ya
        if simulation_cost.historical_ok:
            raise orm.except_orm(_('Error'), _('This cost simulation have '
                                               'Historical'))
        subtotal_others_costs = 0.0
        subtotal_others_sales = 0.0
        subtotal_others_benefit = 0.0
        total_costs = 0.0
        total_sales = 0.0
        total_benefit = 0.0
        total_amortizations = 0.0
        total_indirects = 0.0
        total_amort_indirects = 0.0
        subtotal_net_cost = 0.0
        subtotal_gross_margin = 0.0
        subtotal_contribution_margin = 0.0
        subtotal_net_margin = 0.0
        total_net_cost = 0.0
        total_gross_margin = 0.0
        total_contribution_margin = 0.0
        total_net_margin = 0.0
        net_cost_percentage = 0.0
        gross_margin_percentage = 0.0
        contribution_margin_percentage = 0.0
        net_margin_percentage = 0.0
        total_overhead_costs = 0.0
        total = 0.0
        # trato todas las líneas de tipo "OTHERS"
        for cost_line_id in simulation_cost.others_cost_lines_ids:
            cost_line = cost_line_obj.browse(cr, uid, cost_line_id.id)
            # Calculo el total de compras y el total de ventas
            subtotal_others_costs = (subtotal_others_costs +
                                     cost_line.subtotal_purchase)
            subtotal_others_sales = (subtotal_others_sales +
                                     cost_line.subtotal_sale)
            # Sumo los costes de amortización, y los costes indirectos
            total_amortizations = (total_amortizations +
                                   cost_line.amortization_cost)
            total_indirects = total_indirects + cost_line.indirect_cost
            # Sumo importes para Precio Neto, Margen Bruto, Margen de
            # Contribución, Margen Neto
            if cost_line.type2:
                if cost_line.type2 == 'variable' and cost_line.type3:
                    if cost_line.type3 in ('marketing', 'sale'):
                        subtotal_net_cost = (subtotal_net_cost +
                                             cost_line.subtotal_purchase)
                    else:
                        if cost_line.type3 == 'production':
                            subtotal_gross_margin = (
                                subtotal_gross_margin +
                                cost_line.subtotal_purchase)
                if cost_line.type2 == 'fixed' and cost_line.type3:
                    if cost_line.type3 == 'production':
                        subtotal_contribution_margin = (
                            subtotal_contribution_margin +
                            cost_line.subtotal_purchase)
                    else:
                        if cost_line.type3 in ('marketing', 'sale',
                                               'structureexpenses',
                                               'generalexpenses'):
                            subtotal_net_margin = (subtotal_net_margin +
                                                   cost_line.subtotal_purchase)
        subtotal_others_benefit = (subtotal_others_sales -
                                   subtotal_others_costs)
        # Calculo totales generales
        total_costs = subtotal_others_costs
        total_sales = subtotal_others_sales
        total_benefit = subtotal_others_benefit
        # Calculo el total de amortizaciones + costes indirectos
        total_amort_indirects = total_amortizations + total_indirects
        # Calculo Precio Neto, Margen Bruto, Margen de Contribución, Margen
        # Neto
        total_net_cost = total_sales - subtotal_net_cost
        total_gross_margin = total_net_cost - subtotal_gross_margin
        total_contribution_margin = (total_gross_margin -
                                     subtotal_contribution_margin -
                                     total_indirects)
        total_net_margin = (total_contribution_margin - subtotal_net_margin -
                            total_amortizations - total_costs)
        # Calculo los porcentajes de los importes anteriores
        if total_net_cost > 0 and total_sales > 0:
            net_cost_percentage = (total_net_cost * 100) / total_sales
        if total_gross_margin > 0 and total_sales > 0:
            gross_margin_percentage = (total_gross_margin * 100) / total_sales
        if total_contribution_margin > 0 and total_sales > 0:
            contribution_margin_percentage = ((total_contribution_margin * 100)
                                              / total_sales)
        if total_net_margin > 0 and total_sales > 0:
            net_margin_percentage = (total_net_margin * 100) / total_sales
        if simulation_cost.overhead_costs:
            if simulation_cost.overhead_costs > 0:
                if total_amort_indirects > 0 and total_costs > 0:
                    total_overhead_costs = ((simulation_cost.overhead_costs *
                                             (total_amort_indirects +
                                              total_costs)) / 100)
        total = total_indirects + total_costs + total_overhead_costs
        # Modifico el Objeto con los totales
        vals = {'subtotal5_purchase': subtotal_others_costs,
                'subtotal5_sale': subtotal_others_sales,
                'benefit5': subtotal_others_benefit,
                'subtotal5t_purchase': subtotal_others_costs,
                'subtotal5t_sale': subtotal_others_sales,
                'benefit5t': subtotal_others_benefit,
                'total_costs': total_costs,
                'total_sales': total_sales,
                'total_benefits': total_benefit,
                'total_amortizations': total_amortizations,
                'total_indirects': total_indirects,
                'total_amort_indirects': total_amort_indirects,
                'total_overhead_costs': total_overhead_costs,
                'total': total,
                'net_cost': total_net_cost,
                'net_cost_percentage': net_cost_percentage,
                'gross_margin': total_gross_margin,
                'gross_margin_percentage': gross_margin_percentage,
                'contribution_margin': total_contribution_margin,
                'contribution_margin_percentage':
                    contribution_margin_percentage,
                'net_margin': total_net_margin,
                'net_margin_percentage': net_margin_percentage,
                }
        self.write(cr, uid, simulation_cost.id, vals, *args)
        return True

    def button_confirm_create_sale_order(self, cr, uid, ids, context=None):
        val = True
        for simulation in self.browse(cr, uid, ids, context):
            context.update({'active_id': simulation.id})
            val = {'name': 'Confirm Create Sale Order',
                   'type': 'ir.actions.act_window',
                   'res_model': 'wiz.confirm.create.sale.order',
                   'view_type': 'form',
                   'view_mode': 'form',
                   'nodestroy': True,
                   'target': 'new',
                   'context': context,
                   }
        return val

    # BOTÓN para crear un pedido de venta
    def button_create_sale_order(self, cr, uid, ids, context=None):
        cost_line_obj = self.pool['simulation.cost.line']
        sale_order_obj = self.pool['sale.order']
        sale_line_obj = self.pool['sale.order.line']
        partner_obj = self.pool['res.partner']
        product_obj = self.pool['product.product']
        fiscal_position_obj = self.pool['account.fiscal.position']
        # Leo el Objeto Coste
        simulation_cost = self.browse(cr, uid, ids[0], context=context)
        # valido que no esté historificado ya
        if simulation_cost.historical_ok:
            raise orm.except_orm(_('Error'),
                                 _('You can not generate one Sale Order from '
                                   'one Historical'))
        # Para crear un pedido de venta, la simulación debe de tener
        # asignada un cliente
        if not simulation_cost.partner_id:
            raise orm.except_orm(_('Customer Error'),
                                 _('You must assign a customer to the '
                                   'simulation'))
        # Switch para saber si tengo que grabar SALE.ORDER
        grabar_sale_order = False
        general_datas = {}
        # T R A T O   L I N E A S   "OTHERS"
        others_datas = {}
        for cost_line_id in simulation_cost.others_cost_lines_ids:
            cost_line = cost_line_obj.browse(cr, uid, cost_line_id.id,
                                             context=context)
            # Solo trato la línea si la linea de simulación de coste
            # NO está asociada a ninguna línea de pedido
            if not cost_line.sale_order_line_id:
                if not cost_line.product_id:
                    raise orm.except_orm(_('Create Sale Order Error'),
                                         _('On a line of others lines, needed '
                                           'to define a purchase product'))
                if not cost_line.product_sale_id:
                    raise orm.except_orm(_('Create Sale Order Error'),
                                         _('On a line of others lines, needed '
                                           'to define a sale product'))
                grabar_sale_order = True
                w_generation_type = 0
                if simulation_cost.generate_by_line:
                    w_generation_type = 1
                else:
                    if not cost_line.template_id:
                        w_generation_type = 1
                    else:
                        if not cost_line.template_id.template_product_id:
                            w_generation_type = 1
                        else:
                            w_generation_type = 2
                if w_generation_type == 1:
                    # Si el producto existe en el array sumo su precio de venta
                    encontrado = 0
                    subtotal_sale = 0
                    for data in others_datas:
                        datos_array = others_datas[data]
                        product_sale_id = datos_array['product_sale_id']
                        subtotal_sale = datos_array['subtotal_sale']
                        lines_ids = datos_array['lines_ids']
                        if product_sale_id == cost_line.product_sale_id.id:
                            # Si encuentro el producto de la línea en el array
                            encontrado = 1
                            # incremento el importe de la venta
                            subtotal_sale = (subtotal_sale +
                                             cost_line.subtotal_sale)
                            # Añado el id de la linea de coste al último
                            # parámetro del array
                            lines_ids.append(cost_line_id.id)
                            my_vals = {'subtotal_sale': subtotal_sale,
                                       'lines_ids': lines_ids,
                                       }
                            others_datas[data].update(my_vals)
                    # Si no he encontrado el producto en el array, lo inserto
                    # en la última posición. En el último parámetro se guarda
                    # una lista con todos los id de las líneas de la simulacion
                    # de costes que han participado en la creación de la línea
                    # del pedido de venta
                    if encontrado == 0:
                        my_vals = {'product_sale_id':
                                   cost_line.product_sale_id.id,
                                   'subtotal_sale': cost_line.subtotal_sale,
                                   'name': cost_line.product_sale_id.name,
                                   'lines_ids': [cost_line_id.id],
                                   }
                        others_datas[(cost_line.product_sale_id.id)] = my_vals
                else:
                    encontrado = 0
                    subtotal_sale = 0
                    for data in general_datas:
                        datos_array = general_datas[data]
                        product_sale_id = datos_array['product_sale_id']
                        subtotal_sale = datos_array['subtotal_sale']
                        lines_ids = datos_array['lines_ids']
                        if (product_sale_id ==
                                cost_line.template_id.template_product_id.id):
                            # Si encuentro el producto de la línea en el array
                            encontrado = 1
                            # incremento el importe de la venta
                            subtotal_sale = (subtotal_sale +
                                             cost_line.subtotal_sale)
                            # Añado el id de la linea de coste al último
                            # parámetro del array
                            lines_ids.append(cost_line_id.id)
                            my_vals = {'subtotal_sale': subtotal_sale,
                                       'lines_ids': lines_ids,
                                       }
                            general_datas[data].update(my_vals)
                    # Si no he encontrado el producto en el array, lo inserto
                    # en la última posición. En el último parámetro se guarda
                    # una lista con todos los id de las líneas de la simulacion
                    # de costes que han participado en la creación de la línea
                    # del pedido de venta
                    if encontrado == 0:
                        my_product_id = (
                            cost_line.template_id.template_product_id.id)
                        my_name = (
                            cost_line.template_id.template_product_id.name)
                        my_vals = {'product_sale_id': my_product_id,
                                   'subtotal_sale': cost_line.subtotal_sale,
                                   'name': my_name,
                                   'lines_ids': [cost_line_id.id]
                                   }
                        general_datas[(my_product_id)] = my_vals
        # Si noy hay lineas para grabar, muestro el error
        if not grabar_sale_order:
            raise orm.except_orm(_('Error'), _('No Cost Lines found to Treat'))
        # G R A B O   SALER.ORDER
        # CREO EL OBJETO SALE.ORDER
        # Cojo los datos del cliente
        addr = partner_obj.address_get(cr, uid,
                                       [simulation_cost.partner_id.id],
                                       ['delivery', 'invoice', 'contact'])
        part = partner_obj.browse(cr, uid, simulation_cost.partner_id.id,
                                  context)
        pricelist = (part.property_product_pricelist and
                     part.property_product_pricelist.id or False)
        payment_term = (part.property_payment_term and
                        part.property_payment_term.id or False)
        fiscal_position = (part.property_account_position and
                           part.property_account_position.id or False)
        dedicated_salesman = part.user_id and part.user_id.id or uid
        val = {'partner_id': simulation_cost.partner_id.id,
               'partner_invoice_id': addr['invoice'],
               'partner_order_id': addr['contact'],
               'partner_shipping_id': addr['delivery'],
               'payment_term': payment_term,
               'fiscal_position': fiscal_position,
               'user_id': dedicated_salesman,
               'simulation_cost_ids': [(6, 0, [simulation_cost.id])],
               }
        if pricelist:
            val['pricelist_id'] = pricelist
        # Grabo SALE.ORDER
        sale_order_id = sale_order_obj.create(cr, uid, val, context=context)
        # CREO EL OBJETO SALE.ORDER.LINE PARA CUANDO GENERO LINEAS DE PEDIDOS
        # DE VENTA CON EL PRODUCTO DE LA PLANTILLA
        for data in general_datas:
            # Cojo los datos del array
            datos_array = general_datas[data]
            product_sale_id = datos_array['product_sale_id']
            subtotal_sale = datos_array['subtotal_sale']
            name = datos_array['name']
            lines_ids = datos_array['lines_ids']
            context = {}
            lang = context.get('lang', False)
            context = {'lang': lang,
                       'partner_id': simulation_cost.partner_id.id
                       }
            product_obj = product_obj.browse(cr, uid, product_sale_id,
                                             context=context)
            fpos = (fiscal_position and
                    fiscal_position_obj.browse(cr, uid, fiscal_position,
                                               context=context) or False)
            tax_id = fiscal_position_obj.map_tax(cr, uid, fpos,
                                                 product_obj.taxes_id)
            values_line = {'product_id': product_sale_id,
                           'type': 'make_to_order',
                           'order_id': sale_order_id,
                           'name': name,
                           'product_uom': product_obj.uom_id.id,
                           'price_unit': subtotal_sale,
                           'tax_id': [(6, 0, tax_id)],
                           'simulation_cost_line_ids': [(6, 0, lines_ids)],
                           }
            sale_line_obj.create(cr, uid, values_line, context=context)
        # CREO EL OBJETO SALE.ORDER.LINE PARA OTHERS LINES
        for data in others_datas:
            # Cojo los datos del array
            datos_array = others_datas[data]
            product_sale_id = datos_array['product_sale_id']
            subtotal_sale = datos_array['subtotal_sale']
            name = datos_array['name']
            lines_ids = datos_array['lines_ids']
            context = {}
            lang = context.get('lang', False)
            context = {'lang': lang,
                       'partner_id': simulation_cost.partner_id.id}
            product_obj = product_obj.browse(cr, uid, product_sale_id,
                                             context=context)
            fpos = (fiscal_position and
                    fiscal_position_obj.browse(cr, uid, fiscal_position,
                                               context=context) or False)
            tax_id = fiscal_position_obj.map_tax(cr, uid, fpos,
                                                 product_obj.taxes_id)
            values_line = {'product_id': product_sale_id,
                           'order_id': sale_order_id,
                           'name': name,
                           'type': 'make_to_order',
                           'product_uom': product_obj.uom_id.id,
                           'price_unit': subtotal_sale,
                           'tax_id': [(6, 0, tax_id)],
                           'simulation_cost_line_ids': [(6, 0, lines_ids)],
                           }
            sale_line_obj.create(cr, uid, values_line)
        return True

    # BOTÓN HISTORIFICAR:
    def button_historificar(self, cr, uid, ids, *args):
        # Leo el Objeto Coste
        simulation_cost = self.browse(cr, uid, ids[0], *args)
        # valido que no esté historificado ya
        if simulation_cost.historical_ok:
            raise orm.except_orm(_('Historical Error'),
                                 _('Already Historical'))
        else:
            # Le pongo la fecha del sistema
            fec_histo = time.strftime('%Y-%m-%d')
            # Modifico el Objeto con la fecha de historificación
            # y con un booleano para indicar que el objeto esta historificado
            my_vals = {'historical_date': fec_histo,
                       'historical_ok': True,
                       }
            self.copy(cr, uid, simulation_cost.id, my_vals)
        return True

    # BOTÓN CREAR NUEVA SIMULACION DE COSTES DESDE HISTORICO
    def button_create_newsimu_fromhisto(self, cr, uid, ids, *args):
        new_simulation_cost_obj = self.pool['simulation.cost']
        # Leo el Objeto Simulación de coste
        simulation_cost = self.browse(cr, uid, ids[0], *args)
        # Verifico que no exista una simulacion de coste que no este cancelada
        simulation_cost_obj2 = self.pool['simulation.cost']
        my_search = [('simulation_number', 'like',
                      simulation_cost.simulation_number[1:14]),
                     ('historical_date', '=', None),
                     ('state', '!=', 'canceled')]
        simulation_cost_ids = simulation_cost_obj2.search(cr, uid, my_search,
                                                          *args)
        if simulation_cost_ids:
            raise orm.except_orm(_('Error Creating Simulation Cost'),
                                 _('There is a Simulation Cost'))
        # Copio el objeto simulacion de coste.
        my_vals = {'historical_date': None,
                   'historical_ok': False,
                   }
        cost_simu_id = self.copy(cr, uid, simulation_cost.id, my_vals)
        # Al nuevo objeto simulación de coste le camio el serial
        new_simulation_cost = new_simulation_cost_obj.browse(cr, uid,
                                                             cost_simu_id,
                                                             *args)
        literal = new_simulation_cost.simulation_number + 'H'
        # Actualizo el nuevo objeto de simulación de coste con el nuevo serial
        self.write(cr, uid, [cost_simu_id], {'simulation_number': literal,
                                             }, *args)
        return True

    # BOTÓN COPIAR UNA SIMULACION DE COSTES
    def button_copy_cost_simulation(self, cr, uid, ids, context=None):
        cost_line_obj = self.pool['simulation.cost.line']
        # Leo el Objeto Simulación de coste
        simulation_cost = self.browse(cr, uid, ids[0])
        # Creo la nueva simulacion de costes
        line_vals = {'name': simulation_cost.name,
                     'overhead_costs': simulation_cost.overhead_costs,
                     'subtotal5_purchase': simulation_cost.subtotal5_purchase,
                     'subtotal5_sale': simulation_cost.subtotal5_sale,
                     'benefit5': simulation_cost.benefit5,
                     'subtotal5t_purchase':
                         simulation_cost.subtotal5t_purchase,
                     'subtotal5t_sale': simulation_cost.subtotal5t_sale,
                     'benefit5t': simulation_cost.benefit5t,
                     'total_costs': simulation_cost.total_costs,
                     'total_sales': simulation_cost.total_sales,
                     'total_benefits': simulation_cost.total_benefits,
                     'total_amortizations':
                         simulation_cost.total_amortizations,
                     'total_indirects': simulation_cost.total_indirects,
                     'total_amort_indirects':
                         simulation_cost.total_amort_indirects,
                     'total_overhead_costs':
                         simulation_cost.total_overhead_costs,
                     'total': simulation_cost.total,
                     'net_cost': simulation_cost.net_cost,
                     'net_cost_percentage':
                         simulation_cost.net_cost_percentage,
                     'gross_margin': simulation_cost.gross_margin,
                     'gross_margin_percentage':
                         simulation_cost.gross_margin_percentage,
                     'contribution_margin':
                         simulation_cost.contribution_margin,
                     'contribution_margin_percentage':
                         simulation_cost.contribution_margin_percentage,
                     'net_margin': simulation_cost.net_margin,
                     'net_margin_percentage':
                         simulation_cost.net_margin_percentage,
                     'state': simulation_cost.state,
                     }
        simulation_cost_id = self.create(cr, uid, line_vals, context=context)
        # Copio las lineas de otros
        for others_cost_lines_id in simulation_cost.others_cost_lines_ids:
            cost_line = cost_line_obj.browse(cr, uid, others_cost_lines_id.id,
                                             context=context)
            line_vals = {'simulation_cost_id': simulation_cost_id,
                         'product_id': cost_line.product_id.id,
                         'name': cost_line.name,
                         'description': cost_line.description,
                         'supplier_id': cost_line.supplier_id.id,
                         'purchase_price': cost_line.purchase_price,
                         'uom_id': cost_line.uom_id.id,
                         'amount': cost_line.amount,
                         'product_sale_id': cost_line.product_sale_id.id,
                         'sale_price': cost_line.sale_price,
                         'estimated_margin': cost_line.estimated_margin,
                         'estimated_date_purchase_completion':
                             cost_line.estimated_date_purchase_completion,
                         'amortization_rate': cost_line.amortization_rate,
                         'amortization_cost': cost_line.amortization_cost,
                         'indirect_cost_rate': cost_line.indirect_cost_rate,
                         'indirect_cost': cost_line.indirect_cost,
                         'type_cost': cost_line.type_cost,
                         'type2': cost_line.type2,
                         'type3': cost_line.type3,
                         'template_id': cost_line.template_id.id,
                         }
            cost_line_obj.create(cr, uid, line_vals, context=context)
        value = {'view_type': 'form',
                 'view_mode': 'form,tree',
                 'res_model': 'simulation.cost',
                 'res_id': simulation_cost_id,
                 'context': context,
                 'type': 'ir.actions.act_window',
                 'nodestroy': True
                 }
        return value

    # FUNCIONES PARA EL TRATAMIENTO DEL WORKFLOW
    def action_draft(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state': 'draft'})
        return True

    def action_accepted(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state': 'accepted'})
        return True

    def action_canceled(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state': 'canceled'})
        return True

    # Condicion para ejecutar el estado de workflow correspondiente
    def validar_historical(self, cr, uid, ids):
        simulation_cost = self.browse(cr, uid, ids[0])
        # valido que no esté historificado ya
        if simulation_cost.historical_ok:
            raise orm.except_orm(_('Error'),
                                 _('This cost simulation have Historical'))
        return True


class SimulationCostLine(orm.Model):

    _name = 'simulation.cost.line'
    _description = 'Simulation Cost Line'

    def _subtotal_purchase_ref(self, cr, uid, ids, name, args, context=None):
        res = {}
        for cost_line in self.browse(cr, uid, ids, context=context):
            if cost_line.purchase_price and cost_line.amount:
                res[cost_line.id] = (cost_line.purchase_price *
                                     cost_line.amount)
            else:
                res[cost_line.id] = 0
        return res

    def _subtotal_sale_ref(self, cr, uid, ids, name, args, context=None):
        res = {}
        for cost_line in self.browse(cr, uid, ids, context=context):
            if cost_line.sale_price and cost_line.amount:
                res[cost_line.id] = cost_line.sale_price * cost_line.amount
            else:
                res[cost_line.id] = 0
        return res

    def _benefit_ref(self, cr, uid, ids, name, args, context=None):
        res = {}
        for cost_line in self.browse(cr, uid, ids, context=context):
            if cost_line.subtotal_purchase and cost_line.subtotal_sale:
                res[cost_line.id] = (cost_line.subtotal_sale -
                                     cost_line.subtotal_purchase -
                                     cost_line.amortization_cost -
                                     cost_line.indirect_cost)
            else:
                res[cost_line.id] = 0
        return res

    _columns = {
        'simulation_cost_id': fields.many2one('simulation.cost', 'Cost',
                                              ondelete='cascade'),
        'product_id': fields.many2one('product.product', 'Product',
                                      required=True),
        'name': fields.char('Name', size=64, required=True),
        'description': fields.text('Description'),
        # Proveedor
        'supplier_id': fields.many2one('res.partner', 'Supplier'),
        # Precio de compra
        'purchase_price': fields.float('Cost Price', digits=(7, 2)),
        # Unidad de medida
        'uom_id': fields.many2one('product.uom', 'Default Unit Of Measure',
                                  required=True),
        # Cantidad
        'amount': fields.float('Amount',
                               digits_compute=dp.get_precision('Product UoM')),
        # Subtotal de compra
        'subtotal_purchase':
            fields.function(_subtotal_purchase_ref, method=True, digits=(7, 2),
                            string='Subtotal Purchase', store=False),
        # Producto de venta
        'product_sale_id': fields.many2one('product.product', 'Product'),
        # Precio de venta
        'sale_price': fields.float('Sale Price', digits=(7, 2)),
        # Margen estimado
        'estimated_margin': fields.float('Estimated Margin', digits=(3, 4)),
        # Subtotal de venta
        'subtotal_sale':
            fields.function(_subtotal_sale_ref, method=True, digits=(7, 2),
                            string='Subtotal Sale', store=False),
        # Beneficio
        'benefit':
            fields.function(_benefit_ref, method=True, digits=(7, 2),
                            string='Benefit', store=False),
        # Fecha Estimada de compra o realización
        'estimated_date_purchase_completion':
            fields.date('Estimated Date Purchase Completion'),
        # Tasa de amortizacion
        'amortization_rate': fields.float('Amortization Rate', digits=(3, 2)),
        # Coste de Amortización
        'amortization_cost': fields.float('Amortization Cost', digits=(7, 2)),
        # Tasa Costes Indirectos
        'indirect_cost_rate': fields.float('Indirect Cost Rate',
                                           digits=(3, 2)),
        # Coste de Amortización
        'indirect_cost': fields.float('Indirect Cost', digits=(7, 2)),
        'type_cost': fields.selection([('Purchase', 'Purchase'),
                                       ('Investment', 'Investment'),
                                       ('Subcontracting Services',
                                        'Subcontracting'),
                                       ('Task', 'Internal Task'),
                                       ('Others', 'Others')],
                                      'Type of Cost'),
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
        # Plantilla a la que pertenece la linea
        'template_id': fields.many2one('simulation.template', 'Template'),
        # Línea de Pedido de Venta a la que esta asociada esta línea de coste
        'sale_order_line_id': fields.many2one('sale.order.line',
                                              'Sale Orders Lines'),
        # Copiar informacion de producto de compra en producto de venta
        'purchase_insale':
            fields.related('simulation_cost_id', 'purchase_insale',
                           type='boolean', relation='simulation.cost',
                           string='Copy Purchase information in Sale '
                           'information'),
    }
    _defaults = {
        # c.get('type_cost',False): CON ESTO LO QUE CONSEGUIMOS ES QUE ANTES
        # DE GRABAR EL REGISTRO, RECUPERAMOS EL VALOR DEL CAMPO 'type_cost',
        # QUE LE HEMOS CARGADO EN EL FORM CON EL ATRIBUTO 'context', ESTO LO
        #  HEMOS DEFINIDO EN EL TREE Y EN EL FORM DEL PADRE (template que
        # luego llama a template_line). EN EL FORM DE TEMPLATE_LINE, ESTE
        # CAMPO SE DEFINE COMO INVISIBLE.
        'type_cost': lambda self, cr, uid, c: c.get('type_cost', False),
        'type2': lambda self, cr, uid, c: c.get('type2', False),
        'type3': lambda self, cr, uid, c: c.get('type3', False),
        'amount': 1.0,
        'estimated_date_purchase_completion': fields.date.context_today,
        'purchase_insale': lambda self, cr, uid, c: c.get('purchase_insale',
                                                          False),
    }

    def onchange_product(self, cr, uid, ids, product_id, type, amount,
                         subtotal_purchase, estimated_date_purchase_completion,
                         sale_order_line_id, sale_subtotal, context=None):
        lang_obj = self.pool['res.users']
        product_obj = self.pool['product.product']
        supplierinfo_obj = self.pool['product.supplierinfo']
        partner_obj = self.pool['res.partner']
        if sale_order_line_id:
            raise orm.except_orm(_('Product Error'),
                                 _('Yo can not modify the product, this line '
                                   'belongs to a line of sale order'))
        res = {}
        if not product_id or not type:
            return {'value': res}

        context_user = {'lang': lang_obj.browse(cr, uid, uid).lang}
        product = product_obj.browse(cr, uid, product_id, context=context_user)
        # COJO EL PRIMER PROVEEDOR PARA EL PRODUCTO
        supplierinfo_ids = supplierinfo_obj.search(cr, uid,
                                                   [('product_tmpl_id', '=',
                                                product.product_tmpl_id.id)],
                                                order='sequence')
        if not amount:
            amount = 1.0
        if supplierinfo_ids:
            supplierinfo_id = supplierinfo_obj.browse(cr, uid,
                                                      supplierinfo_ids[0],
                                                      context=context)
            lang = partner_obj.browse(cr, uid, supplierinfo_id.name.id).lang
            # Accedo a datos del producto.
            context_partner = {'lang': lang,
                               'partner_id': supplierinfo_id.name.id}
            product = product_obj.browse(cr, uid, product_id,
                                         context=context_partner)
            # Si no tiene fecha de realización, le pongo la fecha del sistema
            if not estimated_date_purchase_completion:
                estimated_date_purchase_completion = fields.date.context_today
            # Cojo el precio de compra según tablas.
            price = 0
            for pricelist in supplierinfo_id.pricelist_ids:
                if pricelist.min_quantity <= amount:
                    price = pricelist.price
            # Calculo el total compra
            subtotal_purchase = amount * price
            amortization_cost = 0.0
            indirect_cost = 0.0
            # Calculo la amortizacion
            amortization_cost = 0.0
            if product.amortization_rate:
                if product.amortization_rate > 0 and subtotal_purchase > 0:
                    amortization_cost = ((subtotal_purchase *
                                          product.amortization_rate) /
                                         100)
            # Calculo los costes indirectos
            indirect_cost = 0.0
            if product.indirect_cost_rate:
                if product.indirect_cost_rate > 0 and subtotal_purchase > 0:
                    indirect_cost = ((subtotal_purchase *
                                      product.indirect_cost_rate) / 100)
            benefit = (sale_subtotal - subtotal_purchase - amortization_cost -
                       indirect_cost)

            res = {'name': (product.name or ''),
                   'description': (product.description or ''),
                   'purchase_price': price,
                   'uom_id': product.uom_id.id,
                   'amount': amount,
                   'supplier_id': supplierinfo_id.name.id,
                   'subtotal_purchase': subtotal_purchase,
                   'amortization_rate': product.amortization_rate,
                   'amortization_cost': amortization_cost,
                   'indirect_cost_rate': product.indirect_cost_rate,
                   'indirect_cost': indirect_cost,
                   'benefit': benefit,
                   'sale_product_id': product_id,
                   'sale_price': product.list_price
                   }
        else:
            if product.standard_price:
                subtotal_purchase = amount * product.standard_price
            else:
                subtotal_purchase = 0
            amortization_cost = 0.0
            indirect_cost = 0.0
            # Calculo la amortizacion
            amortization_cost = 0.0
            if product.amortization_rate:
                if product.amortization_rate > 0 and subtotal_purchase > 0:
                    amortization_cost = ((subtotal_purchase *
                                          product.amortization_rate) / 100)
            # Calculo los costes indirectos
            indirect_cost = 0.0
            if product.indirect_cost_rate:
                if product.indirect_cost_rate > 0 and subtotal_purchase > 0:
                    indirect_cost = ((subtotal_purchase *
                                      product.indirect_cost_rate) / 100)
            benefit = (sale_subtotal - subtotal_purchase - amortization_cost -
                       indirect_cost)
            res = {'name': (product.name or ''),
                   'description': (product.description or ''),
                   'purchase_price': (product.standard_price or ''),
                   'uom_id': product.uom_id.id,
                   'amount': amount,
                   'supplier_id': None,
                   'subtotal_purchase': subtotal_purchase,
                   'amortization_rate': product.amortization_rate,
                   'amortization_cost': amortization_cost,
                   'indirect_cost_rate': product.indirect_cost_rate,
                   'indirect_cost': indirect_cost,
                   'benefit': benefit,
                   'sale_product_id': product_id,
                   'sale_price': product.list_price
                   }
        return {'value': res}

    # SI CAMBIAN EL PROVEEDOR
    def onchange_supplier(self, cr, uid, ids, supplier_id, type_cost,
                          product_id, amount, uom_id,
                          estimated_date_purchase_completion,
                          subtotal_purchase, sale_price, subtotal_sale,
                          estimated_margin, benefit, sale_order_line_id,
                          context=None):
        partner_obj = self.pool['res.partner']
        product_obj = self.pool['product.product']
        pricelist_obj = self.pool['product.pricelist']
        if sale_order_line_id:
            raise orm.except_orm(_('Supplier Error'),
                                 _('Yo can not modify the supplier, this line '
                                   'belongs to a line of sale order'))
        res = {}
        if not supplier_id:
            return {'value': res}
        if not product_id:
            raise orm.except_orm(_('Supplier Error'),
                                 _('You must select a product'))
        # Accedo a datos del proveedor
        supplier = partner_obj.browse(cr, uid, supplier_id, context=context)
        lang = partner_obj.browse(cr, uid, supplier_id).lang
        pricelist_id = supplier.property_product_pricelist_purchase.id
        # Accedo a datos del producto.
        context_partner = {'lang': lang, 'partner_id': supplier_id}
        product = product_obj.browse(cr, uid, product_id,
                                     context=context_partner)
        # Si no tiene fecha de realización, le pongo la fecha del sistema
        if not estimated_date_purchase_completion:
            estimated_date_purchase_completion = fields.date.context_today
        # Si no tiene cantidad, le pongo 1
        if not amount:
            amount = 1.0
        # Cojo el precio de compra según tablas.
        vals = {'uom': uom_id,
                'date': estimated_date_purchase_completion
                }
        price = pricelist_obj.price_get(cr, uid, [pricelist_id], product.id,
                                        amount, supplier_id,
                                        vals)[pricelist_id]
        # Calculo el total compra
        subtotal_purchase = amount * price
        # Calculo el total venta
        if sale_price > 0:
            subtotal_sale = amount * sale_price
        else:
            subtotal_sale = 0
        # Calculo el margen estimado
        if price > 0 and sale_price > 0:
            estimated_margin = (sale_price/price)-1
        else:
            estimated_margin = 0
        # Calculo el beneficio
        benefit = subtotal_sale - subtotal_purchase
        # Calculo la amortizacion
        amortization_cost = 0.0
        if product.amortization_rate:
            if product.amortization_rate > 0 and subtotal_purchase > 0:
                amortization_cost = ((subtotal_purchase *
                                      product.amortization_rate) / 100)
        # Calculo los costes indirectos
        indirect_cost = 0.0
        if product.indirect_cost_rate:
            if product.indirect_cost_rate > 0 and subtotal_purchase > 0:
                indirect_cost = ((subtotal_purchase *
                                  product.indirect_cost_rate) / 100)
        # Cargo campos de pantalla
        benefit = (subtotal_sale - subtotal_purchase - amortization_cost -
                   indirect_cost)
        res.update({'purchase_price': price,
                    'amount': amount,
                    'estimated_date_purchase_completion':
                        estimated_date_purchase_completion,
                    'subtotal_purchase': subtotal_purchase,
                    'subtotal_sale': subtotal_sale,
                    'estimated_margin': estimated_margin,
                    'benefit': benefit,
                    'amortization_rate': product.amortization_rate,
                    'amortization_cost': amortization_cost,
                    'indirect_cost_rate': product.indirect_cost_rate,
                    'indirect_cost': indirect_cost,
                    })
        return {'value': res}

    # SI CAMBIAN EL PRECIO O CANTIDAD DEL PRODUCTO A COMPRAR, CALCULO EL TOTAL
    def onchange_purchase_price_amount(self, cr, uid, ids, type_cost,
                                       amortization_rate, indirect_cost_rate,
                                       purchase_price, amount,
                                       subtotal_purchase, sale_price,
                                       subtotal_sale, estimated_margin,
                                       benefit, sale_order_line_id,
                                       purchase_insale, context=None):
        if sale_order_line_id:
            raise orm.except_orm(_('Price/Amount Error'),
                                 _('Yo can not modify the price/ammount, this '
                                   'line belongs to a line of sale order'))
        res = {}
        if not purchase_price or not amount:
            return {'value': res}
        # Calculo el total de la compra
        if purchase_price > 0 and amount > 0:
            subtotal_purchase = amount * purchase_price
        else:
            subtotal_purchase = 0
        # Si esta activado copiar informacion de compra en venta
        if purchase_insale:
            sale_price = purchase_price
        # Calculo el total de la venta
        if sale_price > 0 and amount > 0:
            subtotal_sale = amount * sale_price
        else:
            subtotal_sale = 0
        # Calculo el margen estimado
        if purchase_price > 0 and sale_price > 0:
            estimated_margin = (sale_price/purchase_price)-1
        else:
            estimated_margin = 0
        # Calculo el beneficio
        benefit = subtotal_sale - subtotal_purchase
        # Calculo la amortizacion
        amortization_cost = 0.0
        if amortization_rate:
            if amortization_rate > 0 and subtotal_purchase > 0:
                amortization_cost = ((subtotal_purchase * amortization_rate) /
                                     100)
        # Calculo los costes indirectos
        indirect_cost = 0.0
        if indirect_cost_rate:
            if indirect_cost_rate > 0 and subtotal_purchase > 0:
                indirect_cost = (subtotal_purchase * indirect_cost_rate) / 100
        # Cargo campos de pantalla
        benefit = (subtotal_sale - subtotal_purchase - amortization_cost -
                   indirect_cost)
        res.update({'subtotal_purchase': subtotal_purchase,
                    'estimated_margin': estimated_margin,
                    'subtotal_sale': subtotal_sale,
                    'benefit': benefit,
                    'amortization_cost': amortization_cost,
                    'indirect_cost': indirect_cost,
                    'sale_price': sale_price
                    })
        return {'value': res}

    # SI CAMBIA EL TIPO DE COSTE
    def onchange_type_cost(self, cr, uid, ids, type, context=None):
        res = {'product_id': '',
               'name': '',
               'description': '',
               'uom_id': '',
               'supplier_id': '',
               'purchase_price': 0,
               'amount': 0,
               'subtotal_purchase': 0,
               'product_sale_id': '',
               'sale_price': 0,
               'estimated_margin': 0,
               'subtotal_sale': 0,
               'benefit': 0,
               'amortization_rate': 0,
               'amortization_cost': 0,
               'indirect_cost_rate': 0,
               'indirect_cost': 0,
               }
        return {'value': res}

    # SI CAMBIAN EL PRODUCTO DE VENTA
    def onchange_sale_product(self, cr, uid, ids, product_sale_id, product_id,
                              purchase_price, amount, subtotal_sale,
                              estimated_margin, subtotal_purchase, benefit,
                              sale_order_line_id, amortization_cost,
                              indirect_cost, context=None):
        product_obj = self.pool['product.product']
        if sale_order_line_id:
            raise orm.except_orm(_('Sale Product Error'),
                                 _('Yo can not modify the sale product, this '
                                   'line belongs to a line of sale order'))
        res = {}
        if not product_sale_id or not product_id:
            return {'value': res}
        # Cojo datos del producto de venta
        product = product_obj.browse(cr, uid, product_sale_id, context=context)
        if product_sale_id != product_id:
            if not product.sale_ok:
                raise orm.except_orm(_('Sale Product Error'),
                                     _('Product must be to sale OR the same '
                                       'product of purchase'))
        # Calculo el total de la venta
        if product.list_price > 0 and amount > 0:
            subtotal_sale = amount * product.list_price
        else:
            subtotal_sale = 0
        # Calculo el margen estimado
        if purchase_price > 0 and product.standard_price > 0:
            estimated_margin = (product.list_price/purchase_price)-1
        else:
            estimated_margin = 0
        # Calculo el beneficio
        benefit = (subtotal_sale - subtotal_purchase - amortization_cost -
                   indirect_cost)
        # Cargo campos de pantalla
        res.update({'sale_price': product.list_price or '',
                    'estimated_margin': estimated_margin,
                    'subtotal_sale': subtotal_sale,
                    'benefit': benefit,
                    })
        return {'value': res}

    # SI CAMBIAN EL PRECIO DE VENTA
    def onchange_sale_price(self, cr, uid, ids, purchase_price, amount,
                            sale_price, subtotal_sale, estimated_margin,
                            subtotal_purchase, benefit, sale_order_line_id,
                            amortization_cost, indirect_cost, context=None):
        if sale_order_line_id:
            raise orm.except_orm(_('Sale Price Error'),
                                 _('Yo can not modify the sale price, this '
                                   'line belongs to a line of sale order'))

        res = {}
        if not sale_price:
            return {'value': res}
        # Calculo el total de la venta
        if sale_price > 0 and amount > 0:
            subtotal_sale = amount * sale_price
        else:
            subtotal_sale = 0
        # Calculo el margen estimado
        if purchase_price > 0 and sale_price > 0:
            estimated_margin = (sale_price/purchase_price)-1
        else:
            estimated_margin = 0
        # Calculo el beneficio
        benefit = (subtotal_sale - subtotal_purchase - amortization_cost -
                   indirect_cost)
        # Cargo campos de pantalla
        res.update({'estimated_margin': estimated_margin,
                    'subtotal_sale': subtotal_sale,
                    'benefit': benefit,
                    })
        return {'value': res}

    # SI CAMBIAN EL MARGEN ESTIMADO
    def onchange_estimated_margin(self, cr, uid, ids, estimated_margin,
                                  purchase_price, sale_price, amount,
                                  subtotal_sale, subtotal_purchase, benefit,
                                  sale_order_line_id, amortization_cost,
                                  indirect_cost, context=None):
        if sale_order_line_id:
            raise orm.except_orm(_('Estimated Margin Error'),
                                 _('Yo can not modify the estimated margin, '
                                   'this line belongs to a line of sale '
                                   'order'))
        res = {}
        if not estimated_margin:
            return {'value': res}
        # Calculo el precio de venta
        if purchase_price > 0 and estimated_margin > 0:
            sale_price = (1+estimated_margin) * purchase_price
        else:
            sale_price = 0
        # Calculo el total de la venta
        if sale_price > 0 and amount > 0:
            subtotal_sale = amount * sale_price
        else:
            subtotal_sale = 0
        # Calculo el beneficio
        benefit = (subtotal_sale - subtotal_purchase - amortization_cost -
                   indirect_cost)
        # Cargo campos de pantalla
        res.update({'sale_price': sale_price,
                    'subtotal_sale': subtotal_sale,
                    'benefit': benefit,
                    })
        return {'value': res}
