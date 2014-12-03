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
import time
from openerp import netsvc


class SaleOrder(orm.Model):
    _inherit = 'sale.order'

    _columns = {
        # Campo para saber con que costes de simulación está relacionada
        'simulation_cost_ids':
            fields.many2many('simulation.cost', 'simucost_saleorder_rel',
                             'sale_order_id', 'simulation_cost_id',
                             'Simulation Costs', readonly=True),
        # Campo para relacionar el proyecto con el pedido de venta, la relacion
        # es de 1 a 1
        'project2_id': fields.many2one('project.project', 'Project'),
        # Campo para saber que pedidos de compra se han generado a partir de
        # este pedido de venta
        'purchase_order_ids':
            fields.one2many('purchase.order', 'sale_order_id',
                            "Purchase Orders"),
    }

    # Heredo la función que crea albaranes y abastecimientos
    def _create_pickings_and_procurements(self, cr, uid, order, order_lines,
                                          picking_id=False, context=None):
        move_obj = self.pool['stock.move']
        picking_obj = self.pool['stock.picking']
        procurement_obj = self.pool['procurement.order']
        proc_ids = []
        for line in order_lines:
            if line.state == 'done':
                continue
            date_planned = self._get_date_planned(cr, uid, order, line,
                                                  order.date_order,
                                                  context=context)
            if line.product_id:
                if line.product_id.product_tmpl_id.type in ('product',
                                                            'consu'):
                    if not picking_id:
                        vals = self._prepare_order_picking(cr, uid, order,
                                                           context=context)
                        picking_id = picking_obj.create(cr, uid, vals,
                                                        context=context)
                    vals = self._prepare_order_line_move(cr, uid, order, line,
                                                         picking_id,
                                                         date_planned,
                                                         context=context)
                    move_id = move_obj.create(cr, uid, vals, context=context)
                else:
                    # a service has no stock move
                    move_id = False
                if not line.clear_procurement:
                    vals = self._prepare_order_line_procurement(
                        cr, uid, order, line, move_id, date_planned,
                        context=context)
                    proc_id = procurement_obj.create(cr, uid, vals,
                                                     context=context)
                    proc_ids.append(proc_id)
                    line.write({'procurement_id': proc_id})
                    self.ship_recreate(cr, uid, order, line, move_id, proc_id)

        wf_service = netsvc.LocalService("workflow")
        if picking_id:
            wf_service.trg_validate(uid, 'stock.picking', picking_id,
                                    'button_confirm', cr)
        for proc_id in proc_ids:
            wf_service.trg_validate(uid, 'procurement.order', proc_id,
                                    'button_confirm', cr)
        val = {}
        if order.state == 'shipping_except':
            val['state'] = 'progress'
            val['shipped'] = False
            if (order.order_policy == 'manual'):
                for line in order.order_line:
                    if (not line.invoiced) and (line.state not in ('cancel',
                                                                   'draft')):
                        val['state'] = 'manual'
                        break
        order.write(val)
        return True

    # FUNCION QUE SE EJECUTA CUANDO CONFIRMO UN PEDIDO DE VENTA
    def action_wait(self, cr, uid, ids, context=None):
        if not context:
            context = {}
        sale_order_obj = self.pool['sale.order']
        sale_order_line_obj = self.pool['sale.order.line']
        simulation_cost_obj = self.pool['simulation.cost']
        project_obj = self.pool['project.project']
        analytic_obj = self.pool['account.analytic.account']
        simula_line_obj = self.pool['simulation.cost.line']
        template_obj = self.pool['simulation.template']
        # Accedo al PEDIDO DE VENTA
        sale_order2 = sale_order_obj.browse(cr, uid, ids[0], context=context)
        # Recorro las lineas de pedido de venta, si el producto de la linea
        # tiene como metodo de abastecimiento OBTENER PARA STOCK, lo marco
        # para que no genere una excepción de abastecimiento
        for sale_order_line in sale_order2.order_line:
            make_to_stock = True
            if sale_order_line.product_id.product_tmpl_id.route_ids:
                prod_tmpl = sale_order_line.product_id.product_tmpl_id
                for route in prod_tmpl.route_ids:
                    if route.name == 'Make To Order':
                        make_to_stock = False
            else:
                make_to_stock = False
            if make_to_stock:
                sale_order_line_obj.write(cr, uid, [sale_order_line.id],
                                          {'clear_procurement': True},
                                          context=context)
        # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION, COJO LA ÚLTIMA
        # SIMULACIÓN ACTIVA QUE NO ESTE CANCELADA, O LA ÚLTIMA HITORIFICADA
        w_found = 0
        w_simulation_cost_id = 0
        w_maxid = 0
        if sale_order2.simulation_cost_ids:
            # Recorro todas las simulaciones asociadas al pedido de venta
            for simulation_cost in sale_order2.simulation_cost_ids:
                if (not simulation_cost.historical_ok and
                        simulation_cost.state not in ('canceled')):
                    # Si es una simulación activa, me quedo con este id
                    w_found = 1
                    w_simulation_cost_id = simulation_cost.id
                else:
                    # Si no ha encontrado la activa me quedo con la última
                    # simulación de coste historificada (la mas nueva, la de
                    # mayor id)
                    if w_found == 0:
                        if simulation_cost.id > w_maxid:
                            w_maxid = simulation_cost.id
            if w_simulation_cost_id == 0:
                # Si no he encontrado una simulación de coste activa para ese
                # pedido de venta
                if w_maxid == 0:
                    # Si no he encontrado una simulación de coste
                    # historificada para ese pedido de venta
                    raise orm.except_orm(_('Project Creation Error'),
                                         _('Simulation Cost not found'))
                else:
                    # Si no he encontrado una simulación de coste activa para
                    # ese pedido de venta, me quedo con el id de la simulación
                    # de coste historificada mas nueva
                    w_simulation_cost_id = w_maxid
        # Si EL PEDIDO DE VENTA VIENE DE UNA SIMULACIÓN, MIRO SI YA TIENE
        # ASOCIADO UN PROYECTO
        if sale_order2.simulation_cost_ids and not sale_order2.project2_id:
            # SI EL PEDIDO DE VENTA NO TIENE UN PROYECTO ASOCIADO, LO CREO
            # Cojo el nombre de la simulacion
            simulation_cost = simulation_cost_obj.browse(cr, uid,
                                                         w_simulation_cost_id,
                                                         context=context)
            name = ('PROJ ' + simulation_cost.simulation_number + ' / ' +
                    sale_order2.name)
            line = {'name': name,
                    'partner_id': sale_order2.partner_id.id,
                    'simulation_cost_id': simulation_cost.id,
                    'is_project': True
                    }
            project_project_id = project_obj.create(cr, uid, line,
                                                    context=context)
            # Actualizo la cuenta analitica que se ha dado de alta
            # automaticamente al crear el proyecto
            project = project_obj.browse(cr, uid, project_project_id,
                                         context=context)
            name = ('PROJ ' + simulation_cost.simulation_number + ' / ' +
                    sale_order2.name)
            vals = {'name': name,
                    'type': 'view',
                    'state': 'open',
                    'estimated_balance': 0,
                    'estimated_cost': 0,
                    'estimated_sale': 0,
                    'partner_id': sale_order2.partner_id.id,
                    }
            analytic_obj.write(cr, uid, [project.analytic_account_id.id],
                               vals, context=context)
            # Modifico el pedido de venta con el id del proyecto creado
            sale_order_obj.write(cr, uid, [sale_order2.id],
                                 {'project2_id': project_project_id},
                                 context=context)
            # CREO UNA SUBCUENTA ANALITICA POR CADA PESTAÑA DEL SIMULADOR DE
            # COSTES
            condition = [('simulation_cost_id', '=', simulation_cost.id)]
            simulation_line_ids = simula_line_obj.search(cr, uid, condition,
                                                         context=context)
            for simulation_line in simula_line_obj.browse(cr, uid,
                                                          simulation_line_ids,
                                                          context=context):
                if simulation_line.template_id:
                    if (simulation_line.sale_order_line_id.order_id.id ==
                            sale_order2.id):
                        template_id = simulation_line.template_id.id
                        template = template_obj.browse(cr, uid, template_id,
                                                       context=context)
                        w_literal = ('SUBP ' +
                                     simulation_cost.simulation_number +
                                     ' / ' + template.name + ' / ' +
                                     sale_order2.name)
                        # Miro si existe la subcuenta analitica
                        condition = [('name', '=', w_literal)]
                        account_ids = analytic_obj.search(
                            cr, uid, condition, context=context, limit=1)
                        if not account_ids:
                            # Si no existe el subproyecto lo doy de alta
                            my_account = project.analytic_account_id
                            line = {'name': w_literal,
                                    'parent_id': my_account.id,
                                    'partner_id': sale_order2.partner_id.id,
                                    'is_subproject': True
                                    }
                            subproject_id = project_obj.create(cr, uid, line,
                                                               context=context)
                            # Actualizo la subcuenta analitica creada desde el
                            # suproyecto
                            subproj = project_obj.browse(
                                cr, uid, subproject_id, context=context)
                            w_sub_account_id = subproj.analytic_account_id.id
                            vals = {'name': w_literal,
                                    'type': 'normal',
                                    'state': 'open',
                                    'estimated_balance': 0,
                                    'estimated_cost': 0,
                                    'estimated_sale': 0,
                                    }
                            analytic_obj.write(cr, uid, [w_sub_account_id],
                                               vals, context=context)
                            # Borro el subproyecto creado, ya que no nos
                            # interesa tenerlo, solo nos interesa tener la
                            # subcuenta analítica
                            project_obj.unlink(
                                cr, uid, [subproj.id], context=context)
                        else:
                            w_sub_account_id = account_ids[0]
                        # Trato la pestaña Others
                        w_literal2 = w_literal + ' (Others)'
                        condition = [('name', '=', w_literal2)]
                        project_ids = project_obj.search(
                            cr, uid, condition, context=context, limit=1)
                        if not project_ids:
                            # Si no existe el subproyecto lo doy de alta
                            line = {'name': w_literal2,
                                    'parent_id': w_sub_account_id,
                                    'partner_id':
                                        sale_order2.partner_id.id,
                                    'simulation_cost_id2':
                                        w_simulation_cost_id
                                    }
                            subproject_id2 = project_obj.create(
                                cr, uid, line, context=context)
                            # Actualizo la subcuenta analitica creada desde
                            # el suproyecto
                            subproject = project_obj.browse(
                                cr, uid, subproject_id2, context=context)
                            w_sub = subproject.analytic_account_id.id
                            w_sub_account_id2 = w_sub
                            vals = {'name': w_literal2,
                                    'type': 'normal',
                                    'state': 'open',
                                    'estimated_balance': 0,
                                    'estimated_cost': 0,
                                    'estimated_sale': 0,
                                    }
                            analytic_obj.write(cr, uid, [w_sub_account_id2],
                                               vals, context=context)

                        w_literal2 = w_literal + ' (Internal Task)'
                        condition = [('name', '=', w_literal2)]
                        project_ids = project_obj.search(
                            cr, uid, condition, context=context, limit=1)
                        if not project_ids:
                            # Si no existe el subproyecto lo doy de alta
                            line = {'name': w_literal2,
                                    'parent_id': w_sub_account_id,
                                    'partner_id': sale_order2.partner_id.id,
                                    'simulation_cost_id2':
                                        w_simulation_cost_id
                                    }
                            subproject_id2 = project_obj.create(
                                cr, uid, line, context=context)
                            # Actualizo la subcuenta analitica creada desde el
                            # suproyecto
                            subproject = project_obj.browse(
                                cr, uid, subproject_id2, context=context)
                            w_sub = subproject.analytic_account_id.id
                            w_sub_account_id2 = w_sub
                            vals = {'name': w_literal2,
                                    'type': 'normal',
                                    'state': 'open',
                                    'estimated_balance': 0,
                                    'estimated_cost': 0,
                                    'estimated_sale': 0,
                                    }
                            analytic_obj.write(cr, uid, [w_sub_account_id2],
                                               vals, context=context)

            # SI NO VENGO DEL MÓDULO
            # avanzosc_cost_simulator_purchase_requisition
            if 'from_purchase_requisition' not in context:
                # Si el pedido de venta viene de una simulacion, y las lineas
                # de pedido de venta tienen productos que definin una
                # plantilla de simulación, genero pedidos y tareas
                if sale_order2.simulation_cost_ids:
                    self._from_purchase_requisition(cr, uid, sale_order2,
                                                    w_simulation_cost_id,
                                                    project,
                                                    project_project_id,
                                                    context)
        super(SaleOrder, self).action_wait(cr, uid, ids, context=context)
        return True

    def _from_purchase_requisition(self, cr, uid, sale_order2,
                                   simulation_id, project,
                                   project_project_id, context=None):
        sale_order_line_obj = self.pool['sale.order.line']
        for sale_line in sale_order2.order_line:
            if sale_line.simulation_cost_line_ids:
                w_found = 0
                w_cont = 0
                for simulation_line in sale_line.simulation_cost_line_ids:
                    if simulation_line.simulation_cost_id.id == simulation_id:
                        w_cont = w_cont + 1
                        tmpl = simulation_line.template_id
                        if tmpl and tmpl.template_product_id:
                            a = simulation_line.template_id
                            b = a.template_product_id.id
                            if sale_line.product_id.id == b:
                                w_found = w_found + 1
                if w_found > 0 and w_found == w_cont:
                    # Genero pedidos de compra y tareas
                    # Indico que no tiene que generar excepciones de
                    # abastecimiento
                    vals = {'clear_procurement': True,
                            }
                    sale_order_line_obj.write(cr, uid, [sale_line.id],
                                              vals, context=context)
                    # Genero pedidos y tareas
                    for simulation_line in sale_line.simulation_cost_line_ids:
                        found2 = False
                        if (simulation_line.product_id.type == 'product' or
                                simulation_line.product_id.type == 'consu'):
                            if (simulation_line.simulation_cost_id.id ==
                                    simulation_id):
                                found2 = True
                        else:
                            if (simulation_line.product_id.type == 'service'
                                and simulation_line.product_id.procure_method
                                    != 'make_to_stock'):
                                if (simulation_line.product_id.supply_method
                                        == 'buy'):
                                    if (simulation_line.simulation_cost_id.id
                                            == simulation_id):
                                        found2 = True
                                else:
                                    sup = simulation_line.product_id
                                    supply = sup.supply_method
                                    if supply == 'produce':
                                        line = simulation_line
                                        simu_id = line.simulation_cost_id.id
                                        if simu_id == simulation_id:
                                            found2 = True
                        if found2:
                            account_id = project.analytic_account_id.id
                            self._generate_project_task(cr, uid, sale_order2,
                                                        project_project_id,
                                                        simulation_id,
                                                        simulation_line,
                                                        account_id,
                                                        context)
        return True

    def _generate_purchase_order(self, cr, uid, project_project_id, sale_order,
                                 w_simulation_cost_id, simulation_cost_line,
                                 account_analytic_account_id, context=None):
        if context is None:
            context = {}
        user_obj = self.pool['res.users']
        partner_obj = self.pool['res.partner']
        prod_obj = self.pool['product.product']
        acc_pos_obj = self.pool['account.fiscal.position']
        purchase_order_obj = self.pool['purchase.order']
        simulation_cost_obj = self.pool['simulation.cost']
        project_project_obj = self.pool['project.project']
        purchase_type_obj = self.pool['purchase.type']
        purchase_line_obj = self.pool['purchase.order.line']
        supplierinfo_obj = self.pool['product.supplierinfo']
        sequence_obj = self.pool['ir.sequence']
        company = user_obj.browse(cr, uid, uid, context=context).company_id
        simulation_cost = simulation_cost_obj.browse(cr, uid,
                                                     w_simulation_cost_id,
                                                     context=context)
        if simulation_cost_line.supplier_id:
            # SI EL PRODUCTO VIENE CON UN PROVEEDOR EN CONTRETO, TRATO ESE
            # PROVEEDOR MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA ESTE
            # PROVEEDOR QUE VIENE EN LA LÍNEA
            condition = [('sale_order_id', '=', sale_order.id),
                         ('partner_id', '=',
                          simulation_cost_line.supplier_id.id),
                         ('state', '=', 'draft'),
                         ('type_cost', '=', simulation_cost_line.type_cost)]
            purchase_order_id = purchase_order_obj.search(cr, uid, condition,
                                                          context=context)
            res_id = False
            partner = simulation_cost_line.supplier_id
            qty = simulation_cost_line.amount
            partner_id = partner.id
            address_id = partner_obj.address_get(
                cr, uid, [partner_id], ['delivery'])['delivery']
            pricelist_id = partner.property_product_pricelist_purchase.id
            warehouse_id = sale_order.shop_id.warehouse_id.id
            uom_id = simulation_cost_line.uom_id.id
            price = simulation_cost_line.purchase_price
            context.update({'lang': partner.lang, 'partner_id': partner_id})
            product = prod_obj.browse(cr, uid,
                                      simulation_cost_line.product_id.id,
                                      context=context)
            product_tmpl = simulation_cost_line.product_id.product_tmpl_id
            taxes_ids = product_tmpl.supplier_taxes_id
            taxes = acc_pos_obj.map_tax(cr, uid,
                                        partner.property_account_position,
                                        taxes_ids)
            # Llamo a esta función para validar el subproyecto, y aprovecho
            # para imputar en cuenta y en subcuenta analítica, los costes y
            # beneficios estimados.
            # type=1 es una caso especial, porque la línea de
            # pedido de venta no proviene de una simulación de costes,
            # por tanto no sé a que pestaña de simulación de costes
            # proviene (purchase, investment, subcontracting, others)
            # type=2 significa que la línea del pedido de venta
            # no proviene de una plantilla de simulacion, y type=3
            # significa que la línea de pedido de venta proviene
            # de una plantilla de simulación
            w_sale_order_name = sale_order.name
            w_account_analytic_account_id = account_analytic_account_id
            w_imp_purchase = simulation_cost_line.subtotal_purchase
            w_imp_sale = simulation_cost_line.subtotal_sale
            w_text = simulation_cost_line.type_cost
            # Si la línea de simulación de coste viene de una línea de
            # plantilla de simulación le paso su ID
            w_template_id = simulation_cost_line.template_id.id
            w_type = 3
            # Al venir el producto con un proveedor en concreto, sumo el
            # importe de coste a analítica, eso lo indico poniento
            # w_sum_analitic = 1
            w_sum_analitic = 1
            self._sale_validate_subproject_account(
                cr, uid, w_sum_analitic, w_type, w_sale_order_name,
                w_simulation_cost_id, w_template_id,
                w_account_analytic_account_id, w_imp_purchase, w_imp_sale,
                context=context)
            if not purchase_order_id:
                # SI NO EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                line_vals = {'name': simulation_cost_line.name,
                             'product_qty': qty,
                             'product_id': simulation_cost_line.product_id.id,
                             'product_uom': uom_id,
                             'price_unit': price or 0.0,
                             'date_planned': time.strftime('%Y-%m-%d'),
                             'move_dest_id': res_id,
                             'notes': product.description_purchase,
                             'taxes_id': [(6, 0, taxes)],
                             }
                # Cojo el tipo de pedido de compra
                if simulation_cost_line.type_cost == 'Others':
                    condition = [('name', '=', 'Others')]
                    purchase_type_ids = purchase_type_obj.search(
                        cr, uid, condition, context=context)
                    if not purchase_type_ids:
                        raise orm.except_orm(_('Purchase Order Error'),
                                             _('Others literal not found in '
                                               'Table Purchase Type'))
                purchase_type = purchase_type_obj.browse(cr, uid,
                                                         purchase_type_ids[0],
                                                         context=context)
                # COJO LA SECUENCIA
                code = purchase_type.sequence.code
                name = sequence_obj.get(cr, uid, code)
                warehouse = sale_order.shop_id.warehouse_id
                position = (partner.property_account_position and
                            partner.property_account_position.id) or False
                po_vals = {'name': name,
                           'origin': (sale_order.name + ' - ' +
                                      simulation_cost.simulation_number),
                           'partner_id': partner_id,
                           'partner_address_id': address_id,
                           'location_id': warehouse.lot_stock_id.id,
                           'warehouse_id': warehouse_id or False,
                           'pricelist_id': pricelist_id,
                           'date_order': time.strftime('%Y-%m-%d'),
                           'company_id': company.id,
                           'fiscal_position': position,
                           'type': purchase_type.id,
                           'type_cost': simulation_cost_line.type_cost
                           }
                pc = self._sale_order_create_purchase_order(cr, uid, po_vals,
                                                            line_vals,
                                                            context=context)
                # AÑADO EL ID DEL SUBPROYECTO AL PEDIDO DE COMPRA
                vals = {'sale_order_id': sale_order.id,
                        'project3_id': project_project_id,
                        }
                purchase_order_obj.write(cr, uid, [pc], vals, context=context)
                # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA QUE SE HA DADO
                # DE ALTA
                purchase_order_line_ids = purchase_line_obj.search(
                    cr, uid, [('order_id', '=', pc)], context=context)
                if not purchase_order_line_ids:
                    raise orm.except_orm(_('Purchase Order Creation Error'),
                                         _('Purchase Order Line not found(2)'))
                else:
                    purchase_order_line_id = purchase_order_line_ids[0]
                purchaseorder_id = pc
            else:
                # SI EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                # DOY DE ALTA UNA LINEA EN LA LINEA DE PEDIDOS DE COMPRA
                line_vals = {'name': simulation_cost_line.name,
                             'order_id': purchase_order_id[0],
                             'product_qty': qty,
                             'product_id': simulation_cost_line.product_id.id,
                             'product_uom': uom_id,
                             'price_unit': price or 0.0,
                             'date_planned': time.strftime('%Y-%m-%d'),
                             'move_dest_id': res_id,
                             'notes': product.description_purchase,
                             'taxes_id': [(6, 0, taxes)],
                             }
                purchase_order_line_id = purchase_line_obj.create(
                    cr, uid, line_vals, context=context)
                purchaseorder_id = purchase_order_id[0]
            # Llamo a esta función para imputar los costes estimados
            # a la subcuenta analítica expresa de la pestaña de
            # simulación de costes de la que proviene.
            # Además de imputar los costes estimados, también relacionará
            # la línea del pedido de compra, con la subcuenta analítica
            # que le corresponde.
            # type=1 es una caso especial, porque la línea de
            # pedido de venta no proviene de una simulación de costes,
            # por tanto no sé a que pestaña de simulación de costes
            # proviene (purchase, investment, subcontracting, others)
            # type=2 significa que la línea del pedido de venta
            # no proviene de una plantilla de simulacion, y type=3
            # significa que la línea de pedido de venta proviene
            # de una plantilla de simulación
            w_sale_order_name = sale_order.name
            w_account_analytic_account_id = account_analytic_account_id
            w_imp_purchase = simulation_cost_line.subtotal_purchase
            w_imp_sale = simulation_cost_line.subtotal_sale
            # Si la línea de simulación de coste viene de una línea de
            # plantilla de simulación
            w_template_id = simulation_cost_line.template_id.id
            # En este campo le paso el texto del tipo de coste
            # (purchase, investment, subcontracting, task, o others)
            w_text = simulation_cost_line.type_cost
            w_purchase_order_line_id = purchase_order_line_id
            w_type = 3
            # Al venir el producto con un proveedor en concreto, sumo el
            # importe de coste a analítica, eso lo indico poniento
            # w_sum_analitic = 1
            w_sum_analitic = 1
            subanalytic_account_id = self._sale_validate_subanalytic_account(
                cr, uid, w_sum_analitic, w_type, w_text,
                w_purchase_order_line_id, w_sale_order_name,
                w_simulation_cost_id, w_template_id,
                w_account_analytic_account_id, w_imp_purchase, w_imp_sale,
                context=context)
            condition = [('analytic_account_id', '=', subanalytic_account_id)]
            subproject_ids = project_project_obj.search(
                cr, uid, condition, context=context)
            vals = {'project2_id': subproject_ids[0],
                    }
            purchase_order_obj.write(cr, uid, [purchaseorder_id], vals,
                                     context=context)
        else:
            # SI EL PRODUCTO NO VIENE CON UN PROVEEDOR EN CONCRETO, TRATO
            # TODOS SUS PROVEEDORES
            condition = [('product_id', '=',
                          simulation_cost_line.product_id.id)]
            supplierinfo_ids = supplierinfo_obj.search(cr, uid, condition,
                                                       context=context,
                                                       order='sequence')
            if not supplierinfo_ids:
                # Si no hay proveedores definidos para el producto, muestro
                # el error
                name = simulation_cost_line.product_id.name
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('You must define one supplier for the '
                                       '  product: %s') % name)
            else:
                # TRATO TODOS LOS PROVEEDORES ENCONTRADOS PARA EL PRODUCTO,
                # CREARE UN PEDIDO DE COMPRA PARA CADA PROVEEDOR DE ESE
                # PRODUCTO
                # Como el producto no viene con un proveedor en concreto, debo
                # de grabar un pedido de compra por cada proveedor, es por
                # ello que inicializo el  campo w_sum_analitic a 0, e iré
                # sumando 1 a este campo por cada proveedor que trate de ese
                # producto, de esta manera solo imputaré a cuentas analíticas
                # 1 única vez
                w_sum_analitic = 0
                #
                for supplierinfo in supplierinfo_ids:
                    supplierinfo_id = supplierinfo_obj.browse(
                        cr, uid, supplierinfo, context=context)
                    supplier = partner_obj.browse(
                        cr, uid, supplierinfo_id.name.id, context=context)
                    # MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA EL PROVEEDOR
                    # QUE VE VIENE  DE LA BUSQUEDA ANTERIOR
                    condition = [('sale_order_id', '=', sale_order.id),
                                 ('partner_id', '=', supplier.id),
                                 ('state', '=', 'draft'),
                                 ('type_cost', '=',
                                  simulation_cost_line.type_cost)]
                    purchase_order_id = purchase_order_obj.search(
                        cr, uid, condition, context=context)
                    res_id = False
                    # Cojo al proveedor
                    partner = partner_obj.browse(
                        cr, uid, supplierinfo_id.name.id, context=context)
                    # Fin coger proveedor
                    qty = simulation_cost_line.amount
                    partner_id = partner.id
                    address_id = partner_obj.address_get(
                        cr, uid, [partner_id], ['delivery'])['delivery']
                    my_pricelist = partner.property_product_pricelist_purchase
                    pricelist_id = my_pricelist.id
                    warehouse_id = sale_order.shop_id.warehouse_id.id
                    uom_id = simulation_cost_line.uom_id.id
                    price = simulation_cost_line.purchase_price
                    context.update({'lang': partner.lang,
                                    'partner_id': partner_id})
                    product = prod_obj.browse(
                        cr, uid, simulation_cost_line.product_id.id,
                        context=context)
                    my_product = simulation_cost_line.product_id
                    my_tax = my_product.product_tmpl_id.supplier_taxes_id
                    taxes_ids = my_tax
                    taxes = acc_pos_obj.map_tax(
                        cr, uid, partner.property_account_position, taxes_ids)
                    # Llamo a esta función para validar el subproyecto, y
                    # aprovecho para imputar en cuenta y en subcuenta
                    # analítica, los costes y beneficios estimados.
                    # type=1 es una caso especial, porque la línea de
                    # pedido de venta no proviene de una simulación de costes,
                    # por tanto no sé a que pestaña de simulación de costes
                    # proviene (purchase, investment, subcontracting, others)
                    # type=2 significa que la línea del pedido de venta
                    # no proviene de una plantilla de simulacion, y type=3
                    # significa que la línea de pedido de venta proviene
                    # de una plantilla de simulación
                    w_sale_order_name = sale_order.name
                    w_account_analytic_account_id = account_analytic_account_id
                    w_imp_purchase = simulation_cost_line.subtotal_purchase
                    w_imp_sale = simulation_cost_line.subtotal_sale
                    w_text = simulation_cost_line.type_cost
                    # Si la línea de simulación de coste viene de una línea de
                    # plantilla de simulación le paso su ID
                    w_template_id = simulation_cost_line.template_id.id
                    w_type = 3
                    # sumo 1 al campo 2_sum_analitic, de esta manera solo
                    # imputaré costes en análitica 1 sola vez.
                    w_sum_analitic = w_sum_analitic + 1
                    #
                    self._sale_validate_subproject_account(
                        cr, uid, w_sum_analitic, w_type, w_sale_order_name,
                        w_simulation_cost_id, w_template_id,
                        w_account_analytic_account_id, w_imp_purchase,
                        w_imp_sale, context=context)
                    if not purchase_order_id:
                        # SI NO EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                        my_product = simulation_cost_line.product_id
                        line_vals = {'name': simulation_cost_line.name,
                                     'product_qty': qty,
                                     'product_id': my_product.id,
                                     'product_uom': uom_id,
                                     'price_unit': price or 0.0,
                                     'date_planned': time.strftime('%Y-%m-%d'),
                                     'move_dest_id': res_id,
                                     'notes': product.description_purchase,
                                     'taxes_id': [(6, 0, taxes)],
                                     }
                        # Cojo el tipo de pedido de compra
                        if simulation_cost_line.type_cost == 'Others':
                            condition = [('name', '=', 'Others')]
                            purchase_type_ids = purchase_type_obj.search(
                                cr, uid, condition, context=context)
                            if not purchase_type_ids:
                                raise orm.except_orm(_('Purchase Order Error'),
                                                     _('Others literal not '
                                                       'found in Table '
                                                       'Purchase Type'))
                        purchase_type = purchase_type_obj.browse(
                            cr, uid, purchase_type_ids[0], context=context)
                        # COJO LA SECUENCIA
                        code = purchase_type.sequence.code
                        name = sequence_obj.get(cr, uid, code)
                        origin = (sale_order.name + ' - ' +
                                  simulation_cost.simulation_number)
                        warehouse = sale_order.shop_id.warehouse_id
                        fiscal = (partner.property_account_position and
                                  partner.property_account_position.id or
                                  False)
                        po_vals = {'name': name,
                                   'origin': origin,
                                   'partner_id': partner_id,
                                   'partner_address_id': address_id,
                                   'location_id': warehouse.lot_stock_id.id,
                                   'warehouse_id': warehouse_id or False,
                                   'pricelist_id': pricelist_id,
                                   'date_order': time.strftime('%Y-%m-%d'),
                                   'company_id': company.id,
                                   'fiscal_position': fiscal,
                                   'type': purchase_type.id,
                                   'type_cost': simulation_cost_line.type_cost
                                   }
                        pc = self._sale_order_create_purchase_order(
                            cr, uid, po_vals, line_vals, context=context)
                        # AÑADO EL ID DEL SUBPROYECTO AL PEDIDO DE COMPRA
                        vals = {'sale_order_id': sale_order.id,
                                'project3_id': project_project_id,
                                }
                        purchase_order_obj.write(cr, uid, [pc], vals,
                                                 context=context)
                        # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA QUE SE
                        # HA DADO DE ALTA
                        purchase_line_ids = purchase_line_obj.search(
                            cr, uid, [('order_id', '=', pc)], context=context)
                        if not purchase_line_ids:
                            raise orm.except_orm(_('Purchase Order Creation '
                                                   'Error'),
                                                 _('Purchase Order Line not '
                                                   'found(2)'))
                        else:
                            purchase_order_line_id = purchase_line_ids[0]
                        purchaseorder_id = pc
                    else:
                        # SI EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                        # DOY DE ALTA UNA LINEA EN LA LINEA DE PEDIDOS DE
                        # COMPRA
                        my_product = simulation_cost_line.product_id
                        line_vals = {'name': simulation_cost_line.name,
                                     'order_id': purchase_order_id[0],
                                     'product_qty': qty,
                                     'product_id': my_product.id,
                                     'product_uom': uom_id,
                                     'price_unit': price or 0.0,
                                     'date_planned': time.strftime('%Y-%m-%d'),
                                     'move_dest_id': res_id,
                                     'notes': product.description_purchase,
                                     'taxes_id': [(6, 0, taxes)],
                                     }
                        purchase_order_line_id = purchase_line_obj.create(
                            cr, uid, line_vals, context=context)
                        purchaseorder_id = purchase_order_id[0]
                    # Llamo a esta función para imputar los costes estimados
                    # a la subcuenta analítica expresa de la pestaña de
                    # simulación de costes de la que proviene.
                    # Además de imputar los costes estimados, también
                    # relacionará la línea del pedido de compra, con la
                    # subcuenta analítica que le corresponde.
                    # type=1 es una caso especial, porque la línea de
                    # pedido de venta no proviene de una simulación de costes,
                    # por tanto no sé a que pestaña de simulación de costes
                    # proviene (purchase, investment, subcontracting, others)
                    # type=2 significa que la línea del pedido de venta
                    # no proviene de una plantilla de simulacion, y type=3
                    # significa que la línea de pedido de venta proviene
                    # de una plantilla de simulación
                    w_sale_order_name = sale_order.name
                    w_account_analytic_account_id = account_analytic_account_id
                    w_imp_purchase = simulation_cost_line.subtotal_purchase
                    w_imp_sale = simulation_cost_line.subtotal_sale
                    # Si la línea de simulación de coste viene de una línea de
                    # plantilla de simulación
                    w_template_id = simulation_cost_line.template_id.id
                    # En este campo le paso el texto del tipo de coste
                    # (purchase, investment, subcontracting, task, o others)
                    w_text = simulation_cost_line.type_cost
                    w_purchase_order_line_id = purchase_order_line_id
                    w_type = 3

                    subanalytic_id = self._sale_validate_subanalytic_account(
                        cr, uid, w_sum_analitic, w_type, w_text,
                        w_purchase_order_line_id, w_sale_order_name,
                        w_simulation_cost_id, w_template_id,
                        w_account_analytic_account_id, w_imp_purchase,
                        w_imp_sale, context=context)
                    condition = [('analytic_account_id', '=', subanalytic_id)]
                    subproject_ids = project_project_obj.search(
                        cr, uid, condition, context=context)
                    vals = {'project2_id': subproject_ids[0],
                            }
                    purchase_order_obj.write(
                        cr, uid, [purchaseorder_id], vals, context=context)
        return True

    def _sale_order_create_purchase_order(self, cr, uid, po_vals, line_vals,
                                          context=None):
        purchase_type_obj = self.pool['purchase.type']
        purchase_obj = self.pool['purchase.order']
        if not po_vals.get('type'):
            condition = [('name', '=', 'Purchase')]
            purchase_type_ids = purchase_type_obj.search(cr, uid, condition,
                                                         context=context)
            if not purchase_type_ids:
                raise orm.except_orm(_('Purchase Order Error'),
                                     _('Purchase literal not found in Table'
                                       ' Purchase Type'))
            else:
                purchase_type = purchase_type_obj.browse(
                    cr, uid, purchase_type_ids[0], context=context)
                po_vals.update({'type': purchase_type.id})

        po_vals.update({'order_line': [(0, 0, line_vals)]})

        return purchase_obj.create(cr, uid, po_vals, context=context)

    def _sale_validate_subproject_account(self, cr, uid, w_sum_analitic,
                                          w_type, w_sale_order_name,
                                          w_simulation_cost_id, w_template_id,
                                          w_account_analytic_account_id,
                                          w_imp_purchase, w_imp_sale,
                                          context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simulation_template_obj = self.pool['simulation.template']
        analytic_account_obj = ['account.analytic.account']
        # w_sum_analitic = 1 significa que debe de imputar costos en analítica,
        # esto lo hacemos porque si un producto viene sin un proveedor en
        # concreto, realizamos tantos pedidos de compra, como proveedores
        # tenga el producto, pero solo imputamos en cuentas analíticas 1 vez
        #
        # Voy a generar el literal a buscar en subcuenta analítica
        w_literal = ''
        # Cojo el nombre de la simulacion de costes
        simulation_cost = simulation_cost_obj.browse(
            cr, uid, w_simulation_cost_id, context=context)
        # type=1 significa que la línea del pedido de venta, no viene de
        # simulación de costes
        if w_type == 1:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Cost / ' + w_sale_order_name)
        # type=2 significa que la línea del pedido de venta viene de una
        # simulación de costes, pero la línea de simulación de costes de
        # la que viene, no está asociada a ninguna plantilla de simulación
        if w_type == 2:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Template / ' +
                         w_sale_order_name)
        # type=3 significa que la línea del pedido de venta viene de
        # simulación de coste, y que la línea de simulación de coste de la que
        # viene, esta asociada a línea de plantilla de simulación
        if w_type == 3:
            # Cojo el nombre de la plantilla de simulación
            simulation_template = simulation_template_obj.browse(
                cr, uid, w_template_id, context=context)
            # Genero el literal a buscar
            w_literal = ('SUBP ' + simulation_cost.simulation_number + ' / ' +
                         simulation_template.name + ' / ' + w_sale_order_name)
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER
        # SI EXISTE O NO
        sub_account_analytic_account_ids = analytic_account_obj.search(
            cr, uid, [('name', '=', w_literal)], context=context)
        # En este punto debería o no de haber encontrado 1 sola subcuenta
        # analítica
        w_found = 0
        for sub_account_analytic_account in sub_account_analytic_account_ids:
            # Si existe la subcuenta analítica, cojo su ID
            w_found = 1
            sub_account_analytic_account_id = sub_account_analytic_account
        # Si no encuentro el subproyecto, lo creo
        if w_found == 0:
            if w_type == 3:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('Subaccount analytic account not '
                                       'found, literal: %s') % w_literal)
            else:
                line = {'name': w_literal,
                        'parent_id':  w_account_analytic_account_id,
                        'type': 'normal',
                        'state': 'open',
                        'estimated_balance': 0,
                        'estimated_cost': 0,
                        'estimated_sale': 0,
                        }
                sub_account_analytic_account_id = analytic_account_obj.create(
                    cr, uid, line, context=context)
        if w_sum_analitic == 1:
            # MODIFICACION DE LA CUENTA ANALÍTICA (DEL PROYECTO)
            account_analytic_account2 = analytic_account_obj.browse(
                cr, uid, w_account_analytic_account_id, context=context)
            w_estimated_cost = account_analytic_account2.estimated_cost
            w_estimated_cost = w_estimated_cost + w_imp_purchase
            w_estimated_sale = account_analytic_account2.estimated_sale
            w_estimated_sale = w_estimated_sale + w_imp_sale
            w_estimated_balance = w_estimated_sale - w_estimated_cost
            vals = {'estimated_cost': w_estimated_cost,
                    'estimated_sale': w_estimated_sale,
                    'estimated_balance': w_estimated_balance,
                    }
            analytic_account_obj.write(
                cr, uid, [w_account_analytic_account_id], vals,
                context=context)
            # MODIFICACION DE LA SUBCUENTA ANALÍTICA (DEL SUBPROYECTO)
            sub_account_analytic_account2 = analytic_account_obj.browse(
                cr, uid, sub_account_analytic_account_id, context=context)
            w_estimated_cost = sub_account_analytic_account2.estimated_cost
            w_estimated_cost = w_estimated_cost + w_imp_purchase
            w_estimated_sale = sub_account_analytic_account2.estimated_sale
            w_estimated_sale = w_estimated_sale + w_imp_sale
            w_estimated_balance = w_estimated_sale - w_estimated_cost
            vals = {'estimated_cost': w_estimated_cost,
                    'estimated_sale': w_estimated_sale,
                    'estimated_balance': w_estimated_balance
                    }
            analytic_account_obj.write(
                cr, uid, [sub_account_analytic_account_id], vals,
                context=context)
        return sub_account_analytic_account_id

    def _sale_validate_subanalytic_account(self, cr, uid, w_sum_analitic,
                                           w_type, w_text,
                                           w_purchase_order_line_id,
                                           w_sale_order_name,
                                           w_simulation_cost_id,
                                           w_template_id,
                                           w_account_analytic_account_id,
                                           w_imp_purchase, w_imp_sale,
                                           context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simulation_template_obj = self.pool['simulation.template']
        account_obj = self.pool['account.analytic.account']
        purchase_order_line_obj = self.pool['purchase.order.line']
        # w_sum_analitic = 1 significa que debe de imputar costos en
        # analítica, esto lo hacemos porque si un producto viene sin un
        # proveedor en concreto, realizamos tantos pedidos de compra, como
        # proveedores tenga el producto, pero solo imputamos en cuentas
        # analíticas 1 vez
        # Voy a generar el literal a buscar en subcuenta analítica
        w_literal = ''
        sub_account_analytic_account_id2 = 0
        if w_text == 'Task':
            w_text = 'Internal Task'
        # Cojo el nombre de la simulacion de costes
        simulation_cost = simulation_cost_obj.browse(
            cr, uid, w_simulation_cost_id, context=context)
        # type=1 significa que la línea del pedido de venta, no viene de
        # simulación de costes
        if w_type == 1:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Cost / ' + w_sale_order_name)
        # type=2 significa que la línea del pedido de venta viene de una
        # simulación de costes, pero la línea de simulación de costes de
        # la que viene, no está asociada a ninguna plantilla de simulación
        if w_type == 2:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Template / ' +
                         w_sale_order_name)
        # type=3 significa que la línea del pedido de venta viene de
        # simulación de coste, y que la línea de simulación de coste de la que
        # viene, esta asociada a línea de plantilla de simulación
        if w_type == 3:
            # Cojo el nombre de la plantilla de simulación
            simulation_template = simulation_template_obj.browse(
                cr, uid, w_template_id, context=context)
            # Genero el literal a buscar
            w_literal = ('SUBP ' + simulation_cost.simulation_number + ' / ' +
                         simulation_template.name + ' / ' + w_sale_order_name)
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER
        # SI EXISTE O NO
        sub_account_analytic_account_ids = account_obj.search(
            cr, uid, [('name', '=', w_literal)], context=context)
        # En este punto debería o no de haber encontrado 1 sola subcuenta
        # analítica
        w_found = 0
        for sub_account_analytic_account in sub_account_analytic_account_ids:
            # Si existe la subcuenta analítica, cojo su ID
            w_found = 1
            sub_account_analytic_account_id = sub_account_analytic_account
        # Si no encuentro el subproyecto, lo creo
        if w_found == 0:
            raise orm.except_orm(_('Purchase Order Creation Error'),
                                 _('Subaccount analytic account not found, '
                                   'literal: %s') % w_literal)
        if w_type == 1:
            # SI LA LINEA DEL PEDIDO DE VENTA NO VIENE DE UNA LINEA DE
            # SIMULACION DE COSTES, NO TENGO MANERA DE ASIGNARLA A NINGUNA
            # PESTAÑA, PERO LO QUE SI SE ES QUE NO ES UNA TAREA INTERNA
            w_literal2 = w_literal + ' (FROM SALE ORDER unknown tab)'
        else:
            # SI LA LINEA DEL PEDIDO DE VENTA VIENE DE UNA LÍNEA DE SIMULACION
            # DE COSTES TENGO QUE BUSCAR LA SUBCUENTA ANALÍTICA QUE LE
            # CORRESPONDA DEPENDIENDO DE LA PESTAÑA DE LA QUE PROVENGA, ES
            # DECIR... EN LA PANTALLA DE SIMULACIÓN DE COSTES TENEMOS LAS
            # PESTAÑAS: Purchase lines, Investment lines, Subcontractig lines,
            # Task lines, Others lines, PUES TENGO QUE BUSCAR LA SUBCUENTA
            # ANALÍTICA CORRESPONDIENTE A LA SOLAPA DE LA QUE PROVENGA LA
            # LINEA
            # Genero el literal a buscar en Subcuentas Analíticas, en esta
            # búsqueda añado la subcuenta del subproyecto en la búsqueda,#
            # porque la subcuenta analítica que tengo que buscar, debe ser#
            # una hija del subproyecto
            w_literal2 = w_literal + ' (' + w_text + ')'
        condition = [('name', '=', w_literal2),
                     ('parent_id', '=', sub_account_analytic_account_id)]
        account_ids3 = account_obj.search(cr, uid, condition, context=context)
        if account_ids3:
            # Si ha encontrado alguna linea, solo habrá encontrado 1,
            # ya que esta buscado una cuenta en concreto, así que me
            # quedo con su ID
            sub_account_analytic_account_id2 = account_ids3[0]
        else:
            if w_type == 3:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('Subaccount Analytic for tab not '
                                       'found(1), literal: %s') % w_literal2)
            else:
                line = {'name': w_literal2,
                        'parent_id':  sub_account_analytic_account_id,
                        'type': 'normal',
                        'state': 'open',
                        'estimated_balance': 0,
                        'estimated_cost': 0,
                        'estimated_sale': 0,
                        }
                sub_account_analytic_account_id2 = account_obj.create(
                    cr, uid, line, context=context)
        if w_sum_analitic == 1:
            # UNA VEZ LLEGADO A ESTE PUNTO, YA PUEDO HACER LA IMPUTACION DE
            # LAS ESTIMACIONES A LA SUBCUENTA ANALITICA PERTENECIENTE A LA
            # PESTAÑA DE LA SIMULACION DE COSTES
            sub_account_analytic_account2 = account_obj.browse(
                cr, uid, sub_account_analytic_account_id2, context=context)
            w_estimated_cost = sub_account_analytic_account2.estimated_cost
            w_estimated_cost = w_estimated_cost + w_imp_purchase
            w_estimated_sale = sub_account_analytic_account2.estimated_sale
            w_estimated_sale = w_estimated_sale + w_imp_sale
            w_estimated_balance = w_estimated_sale - w_estimated_cost
            vals = {'estimated_cost': w_estimated_cost,
                    'estimated_sale': w_estimated_sale,
                    'estimated_balance': w_estimated_balance
                    }
            account_obj.write(cr, uid, [sub_account_analytic_account_id2],
                              vals, context=context)
        # AHORA ACTUALIZO LA LINEA DE PEDIDO DE COMPRA CON SU SUBCUENTA
        # ANALÍTICA CORRESPONDIENTE
        vals = {'account_analytic_id': sub_account_analytic_account_id2
                }
        purchase_order_line_obj.write(cr, uid, [w_purchase_order_line_id],
                                      vals, context=context)
        return sub_account_analytic_account_id2

    def _generate_project_task(self, cr, uid, sale_order, project_project_id,
                               w_simulation_cost_id, simulation_cost_line,
                               account_analytic_account_id, context=None):
        if context is None:
            context = {}
        project_task_obj = self.pool['project.task']
        user_obj = self.pool['res.users']
        product_obj = self.pool['product.product']
        company = user_obj.browse(cr, uid, uid, context=context).company_id
        w_sale_order_partner_id = sale_order.partner_id.id
        w_sale_order_name = sale_order.name
        w_template_id = simulation_cost_line.template_id.id
        w_account_analytic_account_id = account_analytic_account_id
        w_imp_purchase = simulation_cost_line.subtotal_purchase
        w_imp_sale = simulation_cost_line.subtotal_sale
        w_type = 3
        project_subproject_id = self._sale_project_validate_subproject_account(
            cr, uid, w_type, w_sale_order_name,  w_sale_order_partner_id,
            w_simulation_cost_id, w_template_id, w_account_analytic_account_id,
            w_imp_purchase, w_imp_sale, context=context)
        # COJO EL NOMBRE DEL PRODUCTO DE VENTA DE LA LINEA DE SIMULACION DE
        # COSTES
        cost_product = product_obj.browse(
            cr, uid, simulation_cost_line.product_id.id, context=context)
        sale_product = product_obj.browse(
            cr, uid, simulation_cost_line.product_sale_id.id, context=context)
        # DOY DE ALTA LA TAREA PARA EL SUBPROYECTO
        vals = {'name': simulation_cost_line.name,
                'date_deadline': time.strftime('%Y-%m-%d'),
                'planned_hours': simulation_cost_line.amount,
                'remaining_hours': simulation_cost_line.amount,
                'user_id': simulation_cost_line.product_id.product_manager.id,
                'project_id':  project_subproject_id,
                'project3_id': project_project_id,
                'company_id': company.id,
                'cost_product_name': cost_product.name,
                'sale_product_name': sale_product.name,
                }
        project_task_obj.create(cr, uid, vals, context=context)
        return True

    def _sale_project_validate_subproject_account(
            self, cr, uid, w_type, w_sale_order_name, w_sale_order_partner_id,
            w_simulation_cost_id, w_template_id, w_account_analytic_account_id,
            w_imp_purchase, w_imp_sale, context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simulation_template_obj = self.pool['simulation.template']
        account_obj = self.pool['account.analytic.account']
        # Voy a generar el literal a buscar en subcuenta analítica
        w_literal = ''
        # Cojo el nombre de la simulacion de costes
        simulation_cost = simulation_cost_obj.browse(
            cr, uid, w_simulation_cost_id, context=context)
        # type=1 significa que la línea del pedido de venta, no viene de
        # simulación de costes
        if w_type == 1:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Cost / ' + w_sale_order_name)
        # type=2 significa que la línea del pedido de venta viene de una
        # simulación de costes, pero la línea de simulación de costes de
        # la que viene, no está asociada a ninguna plantilla de simulación
        if w_type == 2:
            # Genero el literal
            w_literal = ('SUBP ' + simulation_cost.simulation_number +
                         ' / NO FROM Simulation Template / ' +
                         w_sale_order_name)
        # type=3 significa que la línea del pedido de venta viene de
        # simulación de coste, y que la línea de simulación de coste de la
        # que viene, esta asociada a línea de plantilla de simulación
        if w_type == 3:
            # Cojo el nombre de la plantilla de simulación
            simulation_template = simulation_template_obj.browse(
                cr, uid, w_template_id, context=context)
            # Genero el literal a buscar
            w_literal = ('SUBP ' + simulation_cost.simulation_number + ' / ' +
                         simulation_template.name + ' / ' + w_sale_order_name)
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER
        # SI EXISTE O NO
        sub_account_analytic_account_ids = account_obj.search(
            cr, uid, [('name', '=', w_literal)], context=context)
        # En este punto debería o no de haber encontrado 1 sola subcuenta
        # analítica
        w_found = 0
        for sub_account_analytic_account in sub_account_analytic_account_ids:
            # Si existe la subcuenta analítica, cojo su ID
            w_found = 1
            sub_account_analytic_account_id = sub_account_analytic_account
        # Si no encuentro el subproyecto, lo creo
        if w_found == 0:
            if w_type == 3:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('Subaccount Analytic account not'
                                       ' found, for literal: %s') % w_literal)
            else:
                line = {'name': w_literal,
                        'parent_id':  w_account_analytic_account_id,
                        'type': 'normal',
                        'state': 'open',
                        'estimated_balance': 0,
                        'estimated_cost': 0,
                        'estimated_sale': 0,
                        }
                sub_account_analytic_account_id = account_obj.create(
                    cr, uid, line, context=context)
        # MODIFICACION DE LA CUENTA ANALÍTICA (DEL PROYECTO)
        account_analytic_account2 = account_obj.browse(
            cr, uid, w_account_analytic_account_id, context=context)
        w_estimated_cost = account_analytic_account2.estimated_cost
        w_estimated_cost = w_estimated_cost + w_imp_purchase
        w_estimated_sale = account_analytic_account2.estimated_sale
        w_estimated_sale = w_estimated_sale + w_imp_sale
        w_estimated_balance = w_estimated_sale - w_estimated_cost
        vals = {'estimated_cost': w_estimated_cost,
                'estimated_sale': w_estimated_sale,
                'estimated_balance': w_estimated_balance
                }
        account_obj.write(cr, uid, [w_account_analytic_account_id], vals,
                          context=context)
        # MODIFICACION DE LA SUBCUENTA ANALÍTICA (DEL SUBPROYECTO)
        sub_account_analytic_account2 = account_obj.browse(
            cr, uid, sub_account_analytic_account_id, context=context)
        w_estimated_cost = sub_account_analytic_account2.estimated_cost
        w_estimated_cost = w_estimated_cost + w_imp_purchase
        w_estimated_sale = sub_account_analytic_account2.estimated_sale
        w_estimated_sale = w_estimated_sale + w_imp_sale
        w_estimated_balance = w_estimated_sale - w_estimated_cost
        vals = {'estimated_cost': w_estimated_cost,
                'estimated_sale': w_estimated_sale,
                'estimated_balance': w_estimated_balance
                }
        account_obj.write(cr, uid, [sub_account_analytic_account_id], vals,
                          context=context)
        # BUSCO LA SUBCUENTA ANALÍTICA PARA LA PESTAÑA 'internal task'
#        w_literal2 = w_literal + ' (Internal Task)'
#        condition = [('name', '=', w_literal2),
#                     ('parent_id', '=', sub_account_analytic_account_id)]
#        account_ids3 = account_obj.search(
#            cr, uid, condition, context=context)
#        if account_ids3:
#            # Si ha encontrado alguna linea, solo habrá encontrado 1,
#            # ya que esta buscado una cuenta en concreto, así que me
#            # quedo con su ID
#            account_id2 = account_ids3[0]
#            condition = [('name', '=', w_literal2)]
#            project_id = project_project_obj.search(cr, uid, condition,
#                                                    context=context)
#            if not project_id:
#                raise orm.except_orm(_('Purchase Order Creation Error'),
#                                     _('subproject not found(2), literal: '
#                                       '%s') % w_literal2)
#            else:
#                project_subproject_id = project_id[0]
#        else:
#            if w_type == 3:
#                raise orm.except_orm(_('Purchase Order Creation Error'),
#                                     _('Subaccount Analytic for tab not '
#                                       'found(1), literal: %s') % w_literal2)
#            else:
#                # Doy de alta el subproyecto
#                line = {'name': w_literal,
#                        'parent_id': w_account_analytic_account_id,
#                        'partner_id':  w_sale_order_partner_id,
#                        }
#                project_subproject_id = project_project_obj.create(
#                    cr, uid, line, context=context)
#                # Actualizo la subcuenta analitica creada desde el suproyecto
#                subproject = project_project_obj.browse(
#                    cr, uid, project_subproject_id, context=context)
#                w_subaccount_id = subproject.analytic_account_id.id
#                vals = {'name': w_literal,
#                        'type': 'normal',
#                        'state': 'open',
#                        'estimated_balance': 0,
#                        'estimated_cost': 0,
#                        'estimated_sale': 0,
#                        }
#                account_obj.write(cr, uid, [w_subaccount_id],
#                                  vals, context=context)
#                line = {'name': w_literal2,
#                        'parent_id':  w_subaccount_id,
#                        'type': 'normal',
#                        'state': 'open',
#                        'estimated_balance': 0,
#                        'estimated_cost': 0,
#                        'estimated_sale': 0,
#                        }
#                account_id2 = account_obj.create(cr, uid, line,
#                                                 context=context)
#                # ahora creo el subproyecto
#                line = {'name': w_literal2,
#                        'analytic_account_id': account_id2,
#                        }
#                project_subproject_id = project_project_obj.create(
#                    cr, uid, line, context=context)
#        # UNA VEZ LLEGADO A ESTE PUNTO, YA PUEDO HACER LA IMPUTACION DE LAS
#        # ESTIMACIONES A LA SUBCUENTA ANALITICA PERTENECIENTE A LA PESTAÑA
#        # DE LA SIMULACION DE COSTES
#        sub_account_analytic_account2 = account_obj.browse(
#            cr, uid, account_id2, context=context)
#        w_estimated_cost = sub_account_analytic_account2.estimated_cost
#        w_estimated_cost = w_estimated_cost + w_imp_purchase
#        w_estimated_sale = sub_account_analytic_account2.estimated_sale
#        w_estimated_sale = w_estimated_sale + w_imp_sale
#        w_estimated_balance = w_estimated_sale - w_estimated_cost
#        vals = {'estimated_cost': w_estimated_cost,
#                'estimated_sale': w_estimated_sale,
#                'estimated_balance': w_estimated_balance
#                }
#        account_obj.write(cr, uid, [account_id2], vals, context=context)

        return False


class SaleOrderLine(orm.Model):
    _inherit = 'sale.order.line'

    _columns = {
        # Este campo estaba de CTA pero ahora no se usara
        'simulation_cost_line_ids':
            fields.one2many('simulation.cost.line', 'sale_order_line_id',
                            'Simulation Costs Lines'),
        # Campo para saber si tengo que generar abastecimeintos
        'clear_procurement': fields.boolean('Crear Procurement'),
    }
