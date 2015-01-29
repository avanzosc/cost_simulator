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
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class ProcurementOrder(orm.Model):
    _inherit = 'procurement.order'

    _columns = {
        'message': fields.char('Latest error', size=164,
                               help='Exception occurred while computing '
                               'procurement orders.'),
    }

    def make_po(self, cr, uid, ids, context=None):
        res = {}
        if context is None:
            context = {}
        seq_obj = self.pool['ir.sequence']
        purchase_obj = self.pool['purchase.order']
        project_obj = self.pool['project.project']
        sale_obj = self.pool['sale.order']
        sale_line_obj = self.pool['sale.order.line']
        simulation_obj = self.pool['simulation.cost']
        purchase_type_obj = self.pool['purchase.type']

        for procurement in self.browse(cr, uid, ids, context=context):
            if (procurement.product_id.type == 'service' and
                    procurement.product_id.procure_method == 'make_to_stock'):
                res[procurement.id] = False
                continue
            # Busco el abastecimiento que esta en ejecución
            condition = [('product_id', '=', procurement.product_id.id),
                         ('state', '=', 'running'),
                         ('group_id', '=', procurement.group_id.id)]
            procurement_ids = self.search(cr, uid, condition, context=context,
                                          limit=1)
            if not procurement_ids:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('Procurement Order with state RUNNING '
                                       'not found'))
            procurement2 = self.browse(cr, uid, procurement_ids[0],
                                       context=context)
            if procurement2.sale_line_id:
                # Accedo a la LINEA DEL PEDIDO DE VENTA
                sale_line = sale_line_obj.browse(
                    cr, uid, procurement2.sale_line_id.id, context=context)
                # Accedo al PEDIDO DE VENTA
                sale_order = sale_obj.browse(cr, uid, sale_line.order_id.id,
                                             context=context)
                # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION, COJO LA
                # ÚLTIMA SIMULACIÓN ACTIVA QUE NO ESTE CANCELADA, O LA ÚLTIMA
                # HISTORIFICADA
                w_found = 0
                simu_id = 0
                w_maxid = 0
                if sale_order.simulation_cost_ids:
                    # Recorro todas las simulaciones asociadas al pedido de
                    # venta
                    for simulation_cost in sale_order.simulation_cost_ids:
                        if ((not simulation_cost.historical_ok) and
                                (simulation_cost.state not in ('canceled'))):
                            # Si es una simulación activa, me quedo con este id
                            w_found = 1
                            simu_id = simulation_cost.id
                        else:
                            # Si no ha encontrado la activa me quedo con la
                            # última simulación de coste historificada (la mas
                            # nueva, la de mayor id)
                            if w_found == 0:
                                if simulation_cost.id > w_maxid:
                                    w_maxid = simulation_cost.id
                    if simu_id == 0:
                        # Si no he encontrado una simulación de coste activa
                        # para ese pedido de venta
                        if w_maxid == 0:
                            # Si no he encontrado una simulación de coste
                            # historificada para eses pedido de venta
                            raise orm.except_orm(_('Purchase Order Creation'
                                                   ' Error'),
                                                 _('Simulation Cost not '
                                                   'found'))
                        else:
                            # Si no he encontrado una simulación de coste
                            # activa para ese pedido de venta, me quedo con el
                            # id de la simulación de coste historificada mas
                            # nueva
                            simu_id = w_maxid
                    # ACCEDO AL OBJETO SIMULACION
                    simulation_cost = simulation_obj.browse(cr, uid, simu_id,
                                                            context=context)
                    if sale_line.simulation_cost_line_ids:
                        w_found = 0
                        w_cont = 0
                        for line in sale_line.simulation_cost_line_ids:
                            if line.simulation_cost_id.id == simu_id:
                                w_cont = w_cont + 1
                                if line.template_id:
                                    tpl = line.template_id.template_product_id
                                    if line.template_id.template_product_id:
                                        if sale_line.product_id.id == tpl.id:
                                            w_found = w_found + 1
                        if w_found > 0:
                            # Genero pedidos de compra y tareas
                            if w_found == w_cont:
                                res[procurement.id] = False
                                continue

            # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION, MIRO SI YA TIENE
            # ASOCIADO UN PROYECTO
            if procurement2.sale_line_id:
                if sale_order.simulation_cost_ids:
                    if not sale_order.project2_id:
                        raise orm.except_orm(_('Purchase Order Creation '
                                               'Error'),
                                             _('Project not found'))
                    else:
                        # SI EL PEDIDO DE VENTA TIENE UN PROYECTO ASOCIADO,
                        # COJO SU ID
                        project_id = sale_order.project2_id.id
                        # Ahora cojo su cuenta analítica
                        project = project_obj.browse(cr, uid, project_id)
                        project_account_id = project.analytic_account_id.id

            # SI EL PEDIDO DE VENTA NO VIENE DE UNA SIMULACION, HAGO EL
            # TRATAMIENTO DE ANTES
            if (not procurement2.sale_line_id or
                    not sale_order.simulation_cost_ids):
                # Llamo con SUPER al método padre
                res = super(ProcurementOrder, self).make_po(
                    cr, uid, [procurement.id], context=context)
            else:
                # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION
                if not sale_line.simulation_cost_line_ids:
                    # SI LA LINEA DEL PEDIDO DE VENTA NO VIENE DE UNA LINEA
                    # DE SIMULACION DE COSTE
                    res = self._saleline_without_simulation(
                        cr, uid, procurement, sale_line, sale_order,
                        simu_id, simulation_cost, project_id,
                        project_account_id, res, context=context)
                else:
                    # SI LA LINEA DEL PEDIDO DE VENTA, VIENE DE UNA LINEA DE
                    # SIMULACIÓN DE COSTE, TRATO TODAS LA LINEAS DE SIMULACION
                    # DE COSTE
                    res = self._saleline_with_simulation(
                        cr, uid, procurement, sale_line, sale_order,
                        simu_id, simulation_cost, project_id,
                        project_account_id, res, context=context)
        return res

    def _saleline_without_simulation(self, cr, uid, procurement, sale_line,
                                     sale_order, simu_id, simulation_cost,
                                     project_id, project_account_id, res,
                                     context=None):
        purchase_obj = self.pool['purchase.order']
        purchase_line_obj = self.pool['purchase.order.line']
        partner_obj = self.pool['res.partner']
        product_obj = self.pool['product.product']
        purchase_type_obj = self.pool['purchase.type']
        sequence_obj = self.pool['ir.sequence']
        supplierinfo_obj = self.pool['product.supplierinfo']
        uom_obj = self.pool['product.uom']
        pricelist_obj = self.pool['product.pricelist']
        project_obj = self.pool['project.project']
        acc_pos_obj = self.pool['account.fiscal.position']
        user_obj = self.pool['res.users']
        company = user_obj.browse(cr, uid, uid, context=context).company_id
        if procurement.product_id.seller_id:
            # SI EL PRODUCTO VIENE CON UN PROVEEDOR EN CONCRETO, TRATO ESE
            # PROVEEDOR MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA ESTE
            # PROVEEDOR QUE VIENE  EN LA LÍNEA
            condition = [('sale_order_id', '=', sale_order.id),
                         ('partner_id', '=',
                          procurement.product_id.seller_id.id),
                         ('state', '=', 'draft'),
                         ('type_cost', '=', 'Purchase')]
            purchase_order_id = purchase_obj.search(cr, uid, condition,
                                                    context=context)
            res_id = procurement.move_dest_id.id
            partner = procurement.product_id.seller_id
            seller_qty = procurement.product_id.seller_qty
            partner_id = partner.id
            pricelist_id = partner.property_product_pricelist_purchase.id
            uom_id = procurement.product_id.uom_po_id.id
            qty = uom_obj._compute_qty(
                cr, uid, procurement.product_uom.id, procurement.product_qty,
                uom_id)
            if seller_qty:
                qty = max(qty, seller_qty)
            price = pricelist_obj.price_get(
                cr, uid, [pricelist_id], procurement.product_id.id, qty,
                partner_id, {'uom': uom_id})[pricelist_id]
            product = product_obj.browse(cr, uid, procurement.product_id.id,
                                         context=context)
            # Llamo a esta función para validar el subproyecto, y aprovecho
            # para imputar en cuenta y eb subcuenta analítica, los costes y
            # beneficios estimados, parámetro type=1 significa que la línea
            # del pedido de venta no viene de simulación de costes
            w_sale_order_name = sale_order.name
            w_template_id = 0
            w_account_analytic_account_id = project_account_id
            w_imp_purchase = qty * price
            w_imp_sale = qty * product.list_price
            # Al venir el producto con un proveedor en concreto, sumo el
            # importe de coste a analítica, eso lo indico poniento
            # w_sum_analitic = 1
            w_sum_analitic = 1
            # w_type = 1 indica que la línea de pedido de venta no viene de
            # una línea de simulación de coste.
            w_type = 1
            self._purchaseval_analytic_account(
                cr, uid, w_sum_analitic, w_type, w_sale_order_name, simu_id,
                w_template_id, w_account_analytic_account_id, w_imp_purchase,
                w_imp_sale, context=context)
            if not purchase_order_id:
                # Si NO EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR, LLAMO
                # AL MÉTODO PADRE PARA REALIZAR EL MISMO TRATAMIENTO
                res = super(ProcurementOrder, self).make_po(
                    cr, uid, [procurement.id], context=context)
                # COJO LA SECUENCIA
                condition = [('code', '=', 'purchase.order')]
                sequence_ids = sequence_obj.search(cr, uid, condition,
                                                   context=context, limit=1)
                if not sequence_ids:
                    raise orm.except_orm(_('Purchase Order Creation Error'),
                                         _('Purchase Order sequence not '
                                           'found'))
                sequence = sequence_obj.browse(cr, uid, sequence_ids[0],
                                               context=context)
                condition = [('sequence', '=', sequence.id)]
                ptype_ids = purchase_type_obj.search(cr, uid, condition,
                                                     context=context, limit=1)
                if not ptype_ids:
                    raise orm.except_orm(_('Purchase Order Creation Error'),
                                         _('Purchase Type not found'))
                purchase_type = purchase_type_obj.browse(
                    cr, uid, ptype_ids[0], context=context)
                code = purchase_type.sequence.code
                seq = sequence_obj.get(cr, uid, code)
                # MODIFICO EL PEDIDO DE COMPRA AÑADIENDOLE EL CODIGO DE PEDIDO
                # DE VENTA, EL PROYECTO, Y EL TIPO DE COMPRA
                pc = res[procurement.id]
                new_vals = {'name': seq,
                            'sale_order_id': sale_order.id,
                            'project3_id': project_id,
                            'origin': (procurement.origin + ' - ' +
                                       simulation_cost.simulation_number),
                            'type_cost': 'Purchase'
                            }
                purchase_obj.write(cr, uid, [pc], new_vals, context=context)
                # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA QUE SE HA DADO DE
                # ALTA
                purchase_line_ids = purchase_line_obj.search(
                    cr, uid, [('order_id', '=', pc)], context=context)
                if not purchase_line_ids:
                    raise orm.except_orm(_('Purchase Order Creation Error'),
                                         _('Purchase Order Line not '
                                           'found(1)'))
                else:
                    purchase_order_line_id = purchase_line_ids[0]
                purchaseorder_id = pc
            else:
                # Si EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR, DOY DE
                # ALTA UNA LINEA EN LA LINEA DE PEDIDOS DE COMPRA
                res_id = procurement.move_dest_id.id
                partner = procurement.product_id.seller_id
                seller_qty = procurement.product_id.seller_qty
                partner_id = partner.id
                pricelist_id = partner.property_product_pricelist_purchase.id
                uom_id = procurement.product_id.uom_po_id.id
                qty = uom_obj._compute_qty(
                    cr, uid, procurement.product_uom.id,
                    procurement.product_qty, uom_id)
                if seller_qty:
                    qty = max(qty, seller_qty)
                price = pricelist_obj.price_get(
                    cr, uid, [pricelist_id], procurement.product_id.id, qty,
                    partner_id, {'uom': uom_id})[pricelist_id]
                schedule_date = self._get_purchase_schedule_date(
                    cr, uid, procurement, company, context=context)
                # Passing partner_id to context for purchase order line
                # integrity of Line name
                context.update({'lang': partner.lang,
                                'partner_id': partner_id})
                product = product_obj.browse(
                    cr, uid, procurement.product_id.id, context=context)
                tmpl = procurement.product_id.product_tmpl_id
                taxes_ids = tmpl.supplier_taxes_id
                taxes = acc_pos_obj.map_tax(
                    cr, uid, partner.property_account_position, taxes_ids)
                mydat = schedule_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                line_vals = {
                    'order_id': purchase_order_id[0],
                    'name': product.partner_ref,
                    'product_qty': qty,
                    'product_id': procurement.product_id.id,
                    'product_uom': uom_id,
                    'price_unit': price or 0.0,
                    'date_planned': mydat,
                    'move_dest_id': res_id,
                    'notes': product.description_purchase,
                    'taxes_id': [(6, 0, taxes)],
                }
                purchase_order_line_id = purchase_line_obj.create(
                    cr, uid, line_vals, context=context)
                purchaseorder_id = purchase_order_id[0]
            # Llamo a esta función para imputar los costes estimados a la
            # subcuenta analítica expresa de la pestaña de simulación de
            # costes de la que proviene.
            # Además de imputar los costes estimados, también relacionará
            # la línea del pedido de compra, con la subcuenta analítica
            # que le corresponde.
            # type=1 es una caso especial, porque la línea de pedido de venta
            # no proviene de una simulación de costes, por tanto no sé a que
            # pestaña de simulación de costes proviene (purchase, investment,
            # subcontracting, others)
            # type=2 significa que la línea del pedido de venta no proviene de
            # una plantilla de simulacion
            # type=3 significa que la línea de pedido de venta proviene de una
            # plantilla de simulación.
            w_template_id = 0
            w_text = ''
            w_purchase_order_line_id = purchase_order_line_id
            # Al venir el producto con un proveedor en concreto, sumo el
            # importe de coste a analítica, eso lo indico poniento
            # w_sum_analitic = 1
            w_sum_analitic = 1
            # w_type = 1 indica que la línea de pedido de venta no viene de
            # una línea de simulación de coste.
            w_type = 1
            saccount_id = self._purchaseva_subanalytic_account(
                cr, uid, w_sum_analitic, w_type, w_text,
                w_purchase_order_line_id, w_sale_order_name, simu_id,
                w_template_id, w_account_analytic_account_id, w_imp_purchase,
                w_imp_sale, context=context)
            subproject_ids = project_obj.search(
                cr, uid, [('analytic_account_id', '=', saccount_id)],
                context=context)
            purchase_obj.write(cr, uid, [purchaseorder_id],
                               {'project2_id': subproject_ids[0]},
                               context=context)
            vals = {'state': 'running',
                    'purchase_line_id': purchase_order_line_id}
            self.write(cr, uid, [procurement.id], vals,
                       context=context)
        else:
            # SI EL PRODUCTO NO VIENE CON UN PROVEEDOR EN CONCRETO, TRATO
            # TODOS SUS PROVEEDORES
            supplierinfo_ids = supplierinfo_obj.search(
                cr, uid, [('product_id', '=', product.id)], context=context)
            if not supplierinfo_ids:
                # Si no hay proveedores definidos para el producto, muestro el
                # error
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('You must define one supplier for the'
                                       ' product: %s') % product.name)
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
                for supplierinfo in supplierinfo_ids:
                    supplierinfo_id = supplierinfo_obj.browse(
                        cr, uid, supplierinfo, context=context)
                    supplier = partner.browse(
                        cr, uid, supplierinfo_id.name.id, context=context)
                    # MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA EL PROVEEDOR
                    # QUE VE VIENE  DE LA BUSQUEDA ANTERIOR
                    condition = [('sale_order_id', '=', sale_order.id),
                                 ('partner_id', '=', supplier.id),
                                 ('state', '=', 'draft'),
                                 ('type_cost', '=', 'Purchase')]
                    purchase_order_id = purchase_obj.search(
                        cr, uid, condition, context=context)
                    res_id = procurement.move_dest_id.id
                    # Cojo al proveedor
                    partner = partner_obj.browse(
                        cr, uid, supplierinfo_id.name.id, context=context)
                    # Fin coger proveedor
                    seller_qty = procurement.product_id.seller_qty
                    partner_id = partner_id.id
                    p = partner.property_product_pricelist_purchase
                    pricelist_id = p.id
                    uom_id = procurement.product_id.uom_po_id.id
                    qty = uom_obj._compute_qty(
                        cr, uid, procurement.product_uom.id,
                        procurement.product_qty, uom_id)
                    if seller_qty:
                        qty = max(qty, seller_qty)
                    price = pricelist_obj.price_get(
                        cr, uid, [pricelist_id], procurement.product_id.id,
                        qty, partner_id, {'uom': uom_id})[pricelist_id]
                    product = product_obj.browse(
                        cr, uid, procurement.product_id.id, context=context)
                    # Llamo a esta función para validar el subproyecto, y
                    # aprovecho para imputar en cuenta y eb subcuenta
                    # analítica, los costes y beneficios estimados, parámetro
                    # type=1 significa que la línea del pedido de venta no
                    # viene de simulación de costes
                    w_sale_order_name = sale_order.name
                    w_template_id = 0
                    w_account_analytic_account_id = project_account_id
                    w_imp_purchase = qty * price
                    w_imp_sale = qty * product.list_price
                    # sumo 1 al campo 2_sum_analitic, de esta manera solo
                    # imputaré costes en análitica 1 sola vez.
                    w_sum_analitic = w_sum_analitic + 1
                    # w_type = 1 indica que la línea de pedido de venta no
                    # viene de una línea de simulación de coste.
                    w_type = 1
                    self._purchaseval_analytic_account(
                        cr, uid, w_sum_analitic, w_type, w_sale_order_name,
                        simu_id, w_template_id, w_account_analytic_account_id,
                        w_imp_purchase, w_imp_sale, context=context)
                    if not purchase_order_id:
                        # Si NO EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR,
                        # LLAMO AL MÉTODO PADRE PARA REALIZAR EL MISMO
                        # TRATAMIENTO
                        res = super(ProcurementOrder, self).make_po(
                            cr, uid, [procurement.id], context=context)
                        # COJO LA SECUENCIA
                        condition = [('code', '=', 'purchase.order')]
                        sequence_ids = sequence_obj.search(
                            cr, uid, condition, context=context, limit=1)
                        if not sequence_ids:
                            raise orm.except_orm(_('Purchase Order Creation '
                                                   'Error'),
                                                 _('Purchase Order sequence '
                                                   'not found'))
                        sequence = sequence_obj.browse(
                            cr, uid, sequence_ids[0], context=context)
                        condition = [('sequence', '=', sequence.id)]
                        ptype_ids = purchase_type_obj.search(
                            cr, uid, condition, context=context, limit=1)
                        if not ptype_ids:
                            raise orm.except_orm(_('Purchase Order Creation '
                                                   'Error'),
                                                 _('Purchase Type not found'))
                        purchase_type = purchase_type_obj.browse(
                            cr, uid, ptype_ids[0], context=context)
                        code = purchase_type.sequence.code
                        seq = sequence_obj.get(cr, uid, code)
                        # MODIFICO EL PEDIDO DE COMPRA AÑADIENDOLE EL CODIGO
                        # DE PROVEEDOR, EL CODIGO DE PEDIDO DE VENTA, EL
                        # PROYECTO, Y EL TIPO DE COMPRA
                        pc = res[procurement.id]
                        vals = {'name': seq,
                                'partner_id': partner_id,
                                'sale_order_id': sale_order.id,
                                'project3_id': project_id,
                                'origin': procurement.origin + ' - ' +
                                simulation_cost.simulation_number,
                                'type_cost': 'Purchase'
                                }
                        purchase_obj.write(cr, uid, [pc], vals,
                                           context=context)
                        # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA QUE SE HA
                        # DADO DE ALTA
                        purchase_line_ids = purchase_line_obj.search(
                            cr, uid, [('order_id', '=', pc)], context=context)
                        if not purchase_line_ids:
                            raise orm.except_orm(_('Purchase Order Creation'
                                                   ' Error'),
                                                 _('Purchase Order Line not'
                                                   ' found(1)'))
                        else:
                            purchase_order_line_id = purchase_line_ids[0]
                        purchaseorder_id = pc
                    else:
                        # Si EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR, DOY
                        # DE ALTA UNA LINEA EN LA LINEA DE PEDIDOS DE COMPRA
                        res_id = procurement.move_dest_id.id
                        partner = partner.obj.browse(
                            cr, uid, supplierinfo_id, context=context)
                        seller_qty = procurement.product_id.seller_qty
                        partner_id = partner.id
                        pricepur = partner.property_product_pricelist_purchase
                        pricelist_id = pricepur.id
                        condition = [('company_id', '=',
                                      procurement.company_id.id or
                                      company.id)]
                        uom_id = procurement.product_id.uom_po_id.id
                        qty = uom_obj._compute_qty(
                            cr, uid, procurement.product_uom.id,
                            procurement.product_qty, uom_id)
                        if seller_qty:
                            qty = max(qty, seller_qty)
                        price = pricelist_obj.price_get(
                            cr, uid, [pricelist_id], procurement.product_id.id,
                            qty, partner_id, {'uom': uom_id})[pricelist_id]
                        schedule_date = self._get_purchase_schedule_date(
                            cr, uid, procurement, company, context=context)
                        # Passing partner_id to context for purchase order
                        # line integrity of Line name
                        context.update({'lang': partner.lang,
                                        'partner_id': partner_id})
                        product = product_obj.browse(
                            cr, uid, procurement.product_id.id,
                            context=context)
                        tmpl = procurement.product_id.product_tmpl_id
                        taxes_ids = tmpl.supplier_taxes_id
                        taxes = acc_pos_obj.map_tax(
                            cr, uid, partner.property_account_position,
                            taxes_ids)
                        d = schedule_date
                        dat = d.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        line_vals = {'order_id': purchase_order_id[0],
                                     'name': product.partner_ref,
                                     'product_qty': qty,
                                     'product_id': procurement.product_id.id,
                                     'product_uom': uom_id,
                                     'price_unit': price or 0.0,
                                     'date_planned': dat,
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
                    # type=1 es una caso especial, porque la línea de pedido
                    # de venta no proviene de una simulación de costes, por
                    # tanto no sé a que pestaña de simulación de costes
                    # proviene (purchase, investment, subcontracting, others)
                    # type=2 significa que la línea del pedido de venta no
                    # proviene de una plantilla de simulacion,
                    # y type=3 significa que la línea de pedido de venta
                    # proviene de una plantilla de simulación.
                    w_template_id = 0
                    w_text = ''
                    w_purchase_order_line_id = purchase_order_line_id
                    w_type = 1
                    saccount_id = self._purchaseva_subanalytic_account(
                        cr, uid, w_sum_analitic, w_type, w_text,
                        w_purchase_order_line_id, w_sale_order_name, simu_id,
                        w_template_id, w_account_analytic_account_id,
                        w_imp_purchase, w_imp_sale, context=context)
                    condition = [('analytic_account_id', '=', saccount_id)]
                    subproject_ids = project_obj.search(cr, uid, condition,
                                                        context=context)
                    vals = {'project2_id': subproject_ids[0]
                            }
                    purchase_obj.write(cr, uid, [purchaseorder_id], vals,
                                       context=context)
                    vals = {'state': 'running',
                            'purchase_line_id': purchase_order_line_id}
                    self.write(cr, uid, [procurement.id], vals,
                               context=context)

        return res

    def _saleline_with_simulation(self, cr, uid, procurement, sale_line,
                                  sale_order, simu_id, simulation_cost,
                                  project_id, project_account_id, res,
                                  context=None):
        purchase_obj = self.pool['purchase.order']
        purchase_line_obj = self.pool['purchase.order.line']
        product_obj = self.pool['product.product']
        purchase_type_obj = self.pool['purchase.type']
        sequence_obj = self.pool['ir.sequence']
        supplierinfo_obj = self.pool['product.supplierinfo']
        partner_obj = self.pool['res.partner']
        acc_pos_obj = self.pool['account.fiscal.position']
        project_obj = self.pool['project.project']
        user_obj = self.pool['res.users']
        company = user_obj.browse(cr, uid, uid, context=context).company_id
        for simulation_cost_line in sale_line.simulation_cost_line_ids:
            # Si la linea de simulación de coste, se corresponde con la linea
            # de simulación de coste perteneciente a la simulación de coste
            # activa o a la última historificada, trato la linea.
            if simulation_cost_line.simulation_cost_id.id == simu_id:
                if simulation_cost_line.supplier_id:
                    # SI EL PRODUCTO VIENE CON UN PROVEEDOR EN CONTRETO, TRATO
                    # ESE PROVEEDOR  MIRO SI YA EXISTE UN PEDIDO DE COMPRA
                    # PARA ESTE PROVEEDOR QUE VIENE  EN LA LÍNEA
                    condition = [('sale_order_id', '=', sale_order.id),
                                 ('partner_id', '=',
                                  simulation_cost_line.supplier_id.id),
                                 ('state', '=', 'draft'),
                                 ('type_cost', '=',
                                  simulation_cost_line.type_cost)]
                    purchase_id = purchase_obj.search(cr, uid, condition,
                                                      context=context)
                    res_id = procurement.move_dest_id.id
                    partner = simulation_cost_line.supplier_id
                    qty = simulation_cost_line.amount
                    partner_id = partner.id
                    plist = partner.property_product_pricelist_purchase
                    pricelist_id = plist.id
                    condition = [('company_id', '=', procurement.company_id.id
                                  or company.id)]
                    uom_id = simulation_cost_line.uom_id.id
                    price = simulation_cost_line.purchase_price
                    schedule_date = self._get_purchase_schedule_date(
                        cr, uid, procurement, company, context=context)
                    purchase_date = self._get_purchase_order_date(
                        cr, uid, procurement, company, schedule_date,
                        context=context)
                    context.update({'lang': partner.lang,
                                    'partner_id': partner_id})
                    product = product_obj.browse(
                        cr, uid, simulation_cost_line.product_id.id,
                        context=context)
                    tmp = simulation_cost_line.product_id.product_tmpl_id
                    taxes_ids = tmp.supplier_taxes_id
                    taxes = acc_pos_obj.map_tax(
                        cr, uid, partner.property_account_position, taxes_ids)
                    # Llamo a esta función para validar el subproyecto, y
                    # aprovecho para imputar en cuenta y en subcuenta
                    # analítica, los costes y beneficios estimados.
                    # type=1 es una caso especial, porque la línea de pedido
                    # de venta no proviene de una simulación de costes, por
                    # tanto no sé a que pestaña de simulación de costes
                    # proviene (purchase, investment, subcontracting, others)
                    # type=2 significa que la línea del pedido de venta no
                    # proviene de una plantilla de simulacion,
                    # y type=3 significa que la línea de pedido de venta
                    # proviene de una plantilla de simulación
                    w_sale_order_name = sale_order.name
                    w_account_analytic_account_id = project_account_id
                    w_imp_purchase = simulation_cost_line.subtotal_purchase
                    w_imp_sale = simulation_cost_line.subtotal_sale
                    w_text = simulation_cost_line.type_cost
                    if not simulation_cost_line.template_id:
                        # Si la linea de simulación de coste no viene de una
                        # línea de plantilla de simulación
                        w_template_id = 0
                        w_type = 2
                    else:
                        # Si la línea de simulación de coste viene de una línea
                        # de plantilla de simulación le paso su ID
                        w_template_id = simulation_cost_line.template_id.id
                        w_type = 3
                    # Al venir el producto con un proveedor en concreto, sumo
                    # el importe de coste a analítica, eso lo indico poniento
                    # w_sum_analitic = 1
                    w_sum_analitic = 1
                    #
                    self._purchaseval_analytic_account(
                        cr, uid, w_sum_analitic, w_type, w_sale_order_name,
                        simu_id, w_template_id, w_account_analytic_account_id,
                        w_imp_purchase, w_imp_sale, context=context)
                    if not purchase_id:
                        # SI NO EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR
                        a = schedule_date
                        dat = a.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        line_vals = {
                            'name': simulation_cost_line.name,
                            'product_qty': qty,
                            'product_id': simulation_cost_line.product_id.id,
                            'product_uom': uom_id,
                            'price_unit': price or 0.0,
                            'date_planned': dat,
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
                                raise orm.except_orm(_('Purchase Order '
                                                       'Creation Error'),
                                                     _('Others literal not '
                                                       'found in Table '
                                                       'Purchase Type'))
                        purchase_type = purchase_type_obj.browse(
                            cr, uid, purchase_type_ids[0], context=context)
                        # COJO LA SECUENCIA
                        code = purchase_type.sequence.code
                        name = sequence_obj.get(cr, uid, code)
                        sim_number = simulation_cost.simulation_number
                        p = purchase_date
                        dat = p.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        pos = (partner.property_account_position and
                               partner.property_account_position.id or False)
                        po_vals = {'name': name,
                                   'origin': (procurement.origin + ' - ' +
                                              sim_number),
                                   'partner_id': partner_id,
                                   'location_id': procurement.location_id.id,
                                   'pricelist_id': pricelist_id,
                                   'date_order': dat,
                                   'company_id': procurement.company_id.id,
                                   'fiscal_position': pos,
                                   'type': purchase_type.id,
                                   'type_cost': simulation_cost_line.type_cost
                                   }
                        res[procurement.id], purchase_line_id = (
                            self.create_proc_purchaseorder(
                                cr, uid, procurement, po_vals, line_vals,
                                context=context))
                        vals = {'state': 'running',
                                'purchase_line_id': purchase_line_id}
                        self.write(cr, uid, [procurement.id], vals,
                                   context=context)
                        # AÑADO EL ID DEL SUBPROYECTO AL PEDIDO DE COMPRA
                        pc = res[procurement.id]
                        vals = {'sale_order_id': sale_order.id,
                                'project3_id': project_id
                                }
                        purchase_obj.write(cr, uid, [pc], vals,
                                           context=context)
                        # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA QUE SE HA
                        # DADO DE ALTA
                        condition = [('order_id', '=', pc)]
                        purchase_line_ids = purchase_line_obj.search(
                            cr, uid, condition, context=context)
                        if not purchase_line_ids:
                            raise orm.except_orm(_('Purchase Order Creation '
                                                   'Error'),
                                                 _('Purchase Order Line not '
                                                   'found(2)'))
                        else:
                            purchase_order_line_id = purchase_line_ids[0]
                        purchaseorder_id = pc
                    else:
                        # SI EXISTE EL PEDIDO DE COMPRA PARA EL PROVEEDOR DOY
                        # DE ALTA UNA LINEA EN LA LINEA DE PEDIDOS DE COMPRA
                        prod_id = simulation_cost_line.product_id.id
                        a = schedule_date
                        dat = a.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        line_vals = {'name': simulation_cost_line.name,
                                     'order_id': purchase_id[0],
                                     'product_qty': qty,
                                     'product_id': prod_id,
                                     'product_uom': uom_id,
                                     'price_unit': price or 0.0,
                                     'date_planned': dat,
                                     'move_dest_id': res_id,
                                     'notes': product.description_purchase,
                                     'taxes_id': [(6, 0, taxes)],
                                     }
                        purchase_order_line_id = purchase_line_obj.create(
                            cr, uid, line_vals, context=context)
                        purchaseorder_id = purchase_id[0]
                        vals = {'state': 'running',
                                'purchase_line_id': purchase_order_line_id}
                        self.write(cr, uid, [procurement.id], vals,
                                   context=context)
                    # Llamo a esta función para imputar los costes estimados
                    # a la subcuenta analítica expresa de la pestaña de
                    # simulación de costes de la que proviene. Además de
                    # imputar los costes estimados, también relacionará la
                    # línea del pedido de compra, con la subcuenta analítica
                    # que le corresponde.
                    # type=1 es una caso especial, porque la línea de pedido
                    # de venta no proviene de una simulación de costes, por
                    # tanto no sé a que pestaña de simulación de costes
                    # proviene (purchase, investment, subcontracting, others)
                    # type=2 significa que la línea del pedido de venta
                    # no proviene de una plantilla de simulacion,
                    # y type=3 significa que la línea de pedido de venta
                    # proviene de una plantilla de simulación
                    w_sale_order_name = sale_order.name
                    w_account_analytic_account_id = project_account_id
                    w_imp_purchase = simulation_cost_line.subtotal_purchase
                    w_imp_sale = simulation_cost_line.subtotal_sale
                    if not simulation_cost_line.template_id:
                        # Si la linea de simulación de coste no viene de una
                        # línea de plantilla de simulación
                        w_template_id = 0
                        # En este campo le paso el texto del tipo de coste
                        # (purchase, investment, subcontracting, task, o
                        # others)
                        w_text = simulation_cost_line.type_cost
                        w_purchase_order_line_id = purchase_order_line_id
                        w_type = 2
                    else:
                        # Si la línea de simulación de coste viene de una
                        # línea de plantilla de simulación
                        w_template_id = simulation_cost_line.template_id.id
                        # En este campo le paso el texto del tipo de coste
                        # (purchase, investment, subcontracting, task, o
                        # others)
                        w_text = simulation_cost_line.type_cost
                        w_purchase_order_line_id = purchase_order_line_id
                        w_type = 3
                    # Al venir el producto con un proveedor en concreto, sumo
                    # el importe de coste a analítica, eso lo indico poniendo
                    # w_sum_analitic = 1
                    w_sum_analitic = 1
                    #
                    saccount_id = self._purchaseva_subanalytic_account(
                        cr, uid, w_sum_analitic, w_type, w_text,
                        w_purchase_order_line_id, w_sale_order_name, simu_id,
                        w_template_id, w_account_analytic_account_id,
                        w_imp_purchase, w_imp_sale, context=context)
                    condition = [('analytic_account_id', '=', saccount_id)]
                    subproject_ids = project_obj.search(cr, uid, condition,
                                                        context=context)
                    vals = {'project2_id': subproject_ids[0]
                            }
                    purchase_obj.write(cr, uid, [purchaseorder_id], vals,
                                       context=context)
                else:
                    # SI EL PRODUCTO NO VIENE CON UN PROVEEDOR EN CONCRETO,
                    # TRATO TODOS SUS PROVEEDORES
                    condition = [('product_id', '=',
                                  simulation_cost_line.product_id.id)]
                    supplierinfo_ids = supplierinfo_obj.search(
                        cr, uid, condition, context=context, order='sequence')
                    if not supplierinfo_ids:
                        # Si no hay proveedores definidos para el producto,
                        # muestro el error
                        name = simulation_cost_line.product_id.name
                        raise orm.except_orm(_('Purchase Order Creation '
                                               'Error'),
                                             _('You must define one supplier '
                                               'for the product: %s') % name)
                    else:
                        # TRATO TODOS LOS PROVEEDORES ENCONTRADOS PARA EL
                        # PRODUCTO, CREARE UN PEDIDO DE COMPRA PARA CADA
                        # PROVEEDOR DE ESE PRODUCTO
                        # Como el producto no viene con un proveedor en
                        # concreto, debo de grabar un pedido de compra por
                        # cada proveedor, es por ello que inicializo el campo
                        # w_sum_analitic a 0, e iré sumando 1 a este campo por
                        # cada proveedor que trate de ese producto, de esta
                        # manera solo imputaré a cuentas analíticas 1 única
                        # vez
                        w_sum_analitic = 0
                        for supplierinfo in supplierinfo_ids:
                            supplierinfo_id = supplierinfo_obj.browse(
                                cr, uid, supplierinfo, context=context)
                            supplier = partner_obj.browse(
                                cr, uid, supplierinfo_id.name.id,
                                context=context)
                            # MIRO SI YA EXISTE UN PEDIDO DE COMPRA PARA EL
                            # PROVEEDOR QUE VE VIENE  DE LA BUSQUEDA ANTERIOR
                            tcost = simulation_cost_line.type_cost
                            condition = [('sale_order_id', '=', sale_order.id),
                                         ('partner_id', '=', supplier.id),
                                         ('state', '=', 'draft'),
                                         ('type_cost', '=', tcost)]
                            purchase_id = purchase_obj.search(
                                cr, uid, condition, context=context)
                            res_id = procurement.move_dest_id.id
                            # Cojo al proveedor
                            partner = partner_obj.browse(
                                cr, uid, supplierinfo_id.name.id,
                                context=context)
                            # Fin coger proveedor
                            qty = simulation_cost_line.amount
                            partner_id = partner.id
                            prcp = partner.property_product_pricelist_purchase
                            pricelist_id = prcp.id
                            condition = [('company_id', '=',
                                          procurement.company_id.id or
                                          company.id)]
                            uom_id = simulation_cost_line.uom_id.id
                            price = simulation_cost_line.purchase_price
                            schedule_date = self._get_purchase_schedule_date(
                                cr, uid, procurement, company, context=context)
                            purchase_date = self._get_purchase_order_date(
                                cr, uid, procurement, company, schedule_date,
                                context=context)
                            context.update({'lang': partner.lang,
                                            'partner_id': partner_id})
                            product = product_obj.browse(
                                cr, uid, simulation_cost_line.product_id.id,
                                context=context)
                            lprod = simulation_cost_line.product_id
                            tax = lprod.product_tmpl_id.supplier_taxes_id
                            taxes_ids = tax
                            taxes = acc_pos_obj.map_tax(
                                cr, uid, partner.property_account_position,
                                taxes_ids)
                            # Llamo a esta función para validar el subproyecto,
                            # y aprovecho para imputar en cuenta y en
                            # subcuenta analítica, los costes y beneficios
                            # estimados.
                            # type=1 es una caso especial, porque la línea de
                            # pedido de venta no proviene de una simulación de
                            # costes, por tanto no sé a que pestaña de
                            # simulación de costes proviene (purchase,
                            # investment, subcontracting, others)
                            # type=2 significa que la línea del pedido de#
                            # venta no proviene de una plantilla de
                            # simulacion,
                            # y type=3 significa que la línea de pedido de
                            # venta provienede una plantilla de simulación
                            w_sale_order_name = sale_order.name
                            w_account_analytic_account_id = project_account_id
                            sl = simulation_cost_line
                            w_imp_purchase = sl.subtotal_purchase
                            w_imp_sale = simulation_cost_line.subtotal_sale
                            w_text = simulation_cost_line.type_cost
                            if not simulation_cost_line.template_id:
                                w_template_id = 0
                                w_type = 2
                            else:
                                # Si la línea de simulación de coste viene de
                                # una línea de plantilla de simulación le paso
                                # su ID
                                template = simulation_cost_line.template_id
                                w_template_id = template.id
                                w_type = 3
                            # sumo 1 al campo 2_sum_analitic, de esta manera
                            # solo imputaré costes en análitica 1 sola vez.
                            w_sum_analitic = w_sum_analitic + 1
                            self._purchaseval_analytic_account(
                                cr, uid, w_sum_analitic, w_type,
                                w_sale_order_name, simu_id, w_template_id,
                                w_account_analytic_account_id, w_imp_purchase,
                                w_imp_sale, context=context)
                            if not purchase_id:
                                # SI NO EXISTE EL PEDIDO DE COMPRA PARA EL
                                # PROVEEDOR
                                lproduct = simulation_cost_line.product_id.id
                                a = schedule_date
                                t = a.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                                line_vals = {
                                    'name': simulation_cost_line.name,
                                    'product_qty': qty,
                                    'product_id': lproduct,
                                    'product_uom': uom_id,
                                    'price_unit': price or 0.0,
                                    'date_planned': t,
                                    'move_dest_id': res_id,
                                    'notes': product.description_purchase,
                                    'taxes_id': [(6, 0, taxes)],
                                    }
                                # Cojo el tipo de pedido de compra
                                if simulation_cost_line.type_cost == 'Others':
                                    condition = [('name', '=', 'Others')]
                                    purchase_ids = purchase_type_obj.search(
                                        cr, uid, condition, context=context)
                                    if not purchase_ids:
                                        raise orm.except_orm(_('Purchase Order'
                                                               ' Error'),
                                                             _('Others literal'
                                                               ' not found in '
                                                               'Table Purchase'
                                                               ' Type'))
                                purchase_type = purchase_type_obj.browse(
                                    cr, uid, purchase_ids[0], context=context)
                                # COJO LA SECUENCIA
                                code = purchase_type.sequence.code
                                name = sequence_obj.get(cr, uid, code,
                                                        context=context)
                                origin = (procurement.origin + ' - ' +
                                          simulation_cost.simulation_number)
                                location = procurement.location_id
                                a = purchase_date
                                dt = a.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                                cpny_id = procurement.company_id.id
                                fpos = (partner.property_account_position and
                                        partner.property_account_position.id
                                        or False)
                                typcost = simulation_cost_line.type_cost
                                po_vals = {'name': name,
                                           'origin': origin,
                                           'partner_id': partner_id,
                                           'location_id': location.id,
                                           'pricelist_id': pricelist_id,
                                           'date_order': dt,
                                           'company_id': cpny_id,
                                           'fiscal_position': fpos,
                                           'type': purchase_type.id,
                                           'type_cost': typcost
                                           }
                                prc_id = procurement.id
                                res[prc_id], purchase_line_id = (
                                    self.create_proc_purchaseorder(
                                        cr, uid, procurement, po_vals,
                                        line_vals, context=context))
                                vals = {'state': 'running',
                                        'purchase_line_id': purchase_line_id
                                        }
                                self.write(cr, uid, [procurement.id], vals,
                                           context=context)
                                # AÑADO EL ID DEL SUBPROYECTO AL PEDIDO DE
                                # COMPRA
                                pc = res[procurement.id]
                                vals = {'sale_order_id': sale_order.id,
                                        'project3_id': project_id
                                        }
                                purchase_obj.write(cr, uid, [pc], vals,
                                                   context=context)
                                # COJO EL ID DE LA LINEA DE PEDIDO DE COMPRA
                                # QUE SE HA DADO DE ALTA
                                purchase_line_ids = purchase_line_obj.search(
                                    cr, uid, [('order_id', '=', pc)],
                                    context=context)
                                if not purchase_line_ids:
                                    raise orm.except_orm(_('Purchase Order '
                                                           'Creation Error'),
                                                         _('Purchase Order '
                                                           'Line not '
                                                           'found(2)'))
                                purchase_order_line_id = purchase_line_ids[0]
                                purchaseorder_id = pc
                            else:
                                # SI EXISTE EL PEDIDO DE COMPRA PARA EL
                                # PROVEEDOR DOY DE ALTA UNA LINEA EN LA LINEA
                                # DE PEDIDOS DE COMPRA
                                simproduct = simulation_cost_line.product_id
                                a = schedule_date
                                dt = a.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                                line_vals = {
                                    'name': simulation_cost_line.name,
                                    'order_id': purchase_id[0],
                                    'product_qty': qty,
                                    'product_id': simproduct.id,
                                    'product_uom': uom_id,
                                    'price_unit': price or 0.0,
                                    'date_planned': dt,
                                    'move_dest_id': res_id,
                                    'notes': product.description_purchase,
                                    'taxes_id': [(6, 0, taxes)],
                                    }
                                purchase_line_id = purchase_line_obj.create(
                                    cr, uid, line_vals, context=context)
                                purchaseorder_id = purchase_id[0]
                                vals = {'state': 'running',
                                        'purchase_line_id': purchase_line_id
                                        }
                                self.write(cr, uid, [procurement.id], vals,
                                           context=context)
                            # Llamo a esta función para imputar los costes
                            # estimados  a la subcuenta analítica expresa de
                            # la pestaña de simulación de costes de la que
                            # proviene. Además de imputar los costes#
                            # estimados, también relacionará la línea del
                            # pedido de compra, con la subcuenta analítica
                            # que le corresponde.
                            # type=1 es una caso especial, porque la línea de
                            # pedido de venta no proviene de una simulación de
                            # costes, por tanto no sé a que pestaña de
                            # simulación de costes proviene (purchase,
                            # investment, subcontracting, others)
                            # type=2 significa que la línea del pedido de
                            # venta no proviene de una plantilla de simulacion,
                            # y type=3
                            # significa que la línea de pedido de venta
                            # proviene de una plantilla de simulación
                            w_sale_order_name = sale_order.name
                            w_account_analytic_account_id = project_account_id
                            sline = simulation_cost_line
                            w_imp_purchase = sline.subtotal_purchase
                            w_imp_sale = simulation_cost_line.subtotal_sale
                            if not simulation_cost_line.template_id:
                                # Si la linea de simulación de coste no viene
                                # de una línea de plantilla de simulación
                                w_template_id = 0
                                # En este campo le paso el texto del tipo de
                                # coste (purchase, investment, subcontracting,
                                # task, o others)
                                w_text = simulation_cost_line.type_cost
                                w_purchase_order_line_id = purchase_line_id
                                w_type = 2
                            else:
                                # Si la línea de simulación de coste viene de
                                # una línea de plantilla de simulación
                                sline = simulation_cost_line
                                w_template_id = sline.template_id.id
                                # En este campo le paso el texto del tipo de
                                # coste (purchase, investment, subcontracting,
                                # task, o others)
                                w_text = simulation_cost_line.type_cost
                                w_purchase_order_line_id = purchase_line_id
                                w_type = 3

                            saccount_id = self._purchaseva_subanalytic_account(
                                cr, uid, w_sum_analitic, w_type, w_text,
                                w_purchase_order_line_id, w_sale_order_name,
                                simu_id, w_template_id,
                                w_account_analytic_account_id, w_imp_purchase,
                                w_imp_sale, context=context)
                            condition = [('analytic_account_id', '=',
                                          saccount_id)]
                            subproject_ids = project_obj.search(
                                cr, uid, condition, context=context)
                            vals = {'project2_id': subproject_ids[0]
                                    }
                            purchase_obj.write(cr, uid, [purchaseorder_id],
                                               vals, context=context)

        return res

    # HEREDO ESTA FUNCION QUE CREA LA ORDEN DE PEDIDO DE COMPRA
    def create_proc_purchaseorder(self, cr, uid, procurement, po_vals,
                                  line_vals, context=None):
        # MODIFICACION: Si no viene un parametro con nombre 'type',
        # significa que no viene de una simulación, por lo tanto lo
        # ponemos el campo "type" como de compras (este campo indica
        # que tipo de de pedido de compra es, y servirá para generar
        # el código del pedido de compra
        purchase_type_obj = self.pool['purchase.type']
        purchase_obj = self.pool['purchase.order']
        if not po_vals.get('type'):
            purchase_type_ids = purchase_type_obj.search(
                cr, uid, [('name', '=', 'Others')], context=context)
            if not purchase_type_ids:
                raise orm.except_orm(_('Purchase Order Creation Error'),
                                     _('"Others" literal not found in Table '
                                       'Purchase Type'))
            else:
                purchase_type = purchase_type_obj.browse(
                    cr, uid, purchase_type_ids[0], context=context)
                po_vals.update({'type': purchase_type.id})

        po_vals.update({'order_line': [(0, 0, line_vals)]})
        purchase_id = purchase_obj.create(cr, uid, po_vals, context=context)
        purchase = purchase_obj.browse(cr, uid, purchase_id, context=context)
        for line in purchase.order_line:
            purchase_line_id = line.id
        return purchase_id, purchase_line_id

    # Funcion para validar que existe la subcuenta analitica, si no existe la
    # subcuenta analitica la crea, y tambien crea su subproyecto. En esta
    # funcion tambien se realiza la imputacion de la estimacion de costes y
    # beneficios en la subcuenta analitica
    def _purchaseval_analytic_account(self, cr, uid, w_sum_analitic, w_type,
                                      w_sale_order_name, simu_id,
                                      w_template_id,
                                      w_account_analytic_account_id,
                                      w_imp_purchase, w_imp_sale,
                                      context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simtemplate_obj = self.pool['simulation.template']
        account_obj = self.pool['account.analytic.account']
        # w_sum_analitic = 1 significa que debe de imputar costos en
        # analítica, esto lo hacemos porque si un producto viene sin un
        # proveedor en concreto, realizamos tantos pedidos de compra, como
        # proveedores tenga el producto, pero solo imputamos en cuentas
        # analíticas 1 vez

        # Voy a generar el literal a buscar en subcuenta analítica
        w_literal = ''
        # Cojo el nombre de la simulacion de costes

        simulation_cost = simulation_cost_obj.browse(cr, uid, simu_id,
                                                     context=context)
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
            simulation_template = simtemplate_obj.browse(
                cr, uid, w_template_id, context=context)
            # Genero el literal a buscar
            w_literal = ('SUBP ' + simulation_cost.simulation_number + ' / ' +
                         simulation_template.name + ' / ' + w_sale_order_name)
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER SI
        # EXISTE O NO
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
                                     _('Subaccount analytic account not found,'
                                       ' literal: %s') % w_literal)
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

        if w_sum_analitic == 1:
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
            account_obj.write(cr, uid, [sub_account_analytic_account_id],
                              vals, context=context)

        return sub_account_analytic_account_id

    def _purchaseva_subanalytic_account(self, cr, uid, w_sum_analitic, w_type,
                                        w_text, w_purchase_order_line_id,
                                        w_sale_order_name, simu_id,
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
#
        # Voy a generar el literal a buscar en subcuenta analítica
        w_literal = ''
        sub_account_analytic_account_id2 = 0
        if w_text == 'Task':
            w_text = 'Internal Task'
        # Cojo el nombre de la simulacion de costes
        simulation_cost = simulation_cost_obj.browse(cr, uid, simu_id,
                                                     context=context)
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
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER SI
        # EXISTE O NO
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
                                 _('Subaccount Analytic Account not found(1), '
                                   'literal: %s') % w_literal)
        if w_type == 1:
            # SI LA LINEA DEL PEDIDO DE VENTA NO VIENE DE UNA LINEA DE
            # SIMULACION DE COSTES, NO TENGO MANERA DE ASIGNARLA A NINGUNA
            # PESTAÑA, PERO LO QUE SI SE ES QUE NO
            # ES UNA TAREA INTERNA
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
            # porque la subcuenta analítica que tengo que buscar, debe ser una
            # hija del subproyecto
            w_literal2 = w_literal + ' (' + w_text + ')'

        condition = [('name', '=', w_literal2),
                     ('parent_id', '=', sub_account_analytic_account_id)]
        account_ids3 = account_obj.search(cr, uid, condition, context=context)
        if account_ids3:
            # Si ha encontrado alguna linea, solo habrá encontrado 1, ya que
            # esta buscado una cuenta en concreto, así que me  quedo con su ID
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

    def _create_service_task(self, cr, uid, procurement, context=None):
        task_obj = self.pool['project.task']
        sale_order_obj = self.pool['sale.order']
        sale_order_line_obj = self.pool['sale.order.line']
        product_obj = self.pool['product.product']
        project_obj = self.pool['project.project']
        task_id = False
        project = self._get_project(cr, uid, procurement, context=context)
        planned_hours = self._convert_qty_company_hours(
            cr, uid, procurement, context=context)
        # Accedo a la LINEA DEL PEDIDO DE VENTA
        sale_order_line = sale_order_line_obj.browse(
            cr, uid, procurement.sale_line_id.id, context=context)
        # Accedo al PEDIDO DE VENTA
        sale_order = sale_order_obj.browse(
            cr, uid, sale_order_line.order_id.id, context=context)
        # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION, COJO LA ÚLTIMA#
        # SIMULACIÓN ACTIVA QUE NO ESTE CANCELADA, O LA ÚLTIMA
        # HITORIFICADA
        w_found = 0
        w_simulation_cost_id = 0
        w_maxid = 0
        if sale_order.simulation_cost_ids:
            # Recorro todas las simulaciones asociadas al pedido de venta
            for simulation_cost in sale_order.simulation_cost_ids:
                if ((not simulation_cost.historical_ok) and
                        (simulation_cost.state not in ('canceled'))):
                    # Si es una simulación activa, me quedo con este id
                    w_found = 1
                    w_simulation_cost_id = simulation_cost.id
                else:
                    # Si no ha encontrado la activa me quedo con la última
                    # simulación de coste historificada (la mas nueva, la
                    # de mayor id)
                    if w_found == 0:
                        if simulation_cost.id > w_maxid:
                            w_maxid = simulation_cost.id

            if w_simulation_cost_id == 0:
                # Si no he encontrado una simulación de coste activa para
                # ese pedido de venta
                if w_maxid == 0:
                    # Si no he encontrado una simulación de coste
                    # historificada para ese pedido de venta
                    raise orm.except_orm(_('Project Creation Error'),
                                         _('Simulation Cost not found'))
                else:
                    # Si no he encontrado una simulación de coste activa
                    # para ese pedido de venta, me quedo con el id de la
                    # simulación de coste historificada mas nueva
                    w_simulation_cost_id = w_maxid

        if sale_order_line.simulation_cost_line_ids:
            w_found = 0
            w_cont = 0
            for line in sale_order_line.simulation_cost_line_ids:
                if line.simulation_cost_id.id == w_simulation_cost_id:
                    w_cont = w_cont + 1
                    if line.template_id:
                        if line.template_id.template_product_id:
                            tmpl = line.template_id.template_product_id
                            if sale_order_line.product_id.id == tmpl.id:
                                w_found = w_found + 1
            if w_found > 0:
                # Genero pedidos de compra y tareas
                if w_found == w_cont:
                    return task_id

        # Si EL PEDIDO DE VENTA VIENE DE UNA SIMULACIÓN, MIRO SI YA
        # TIENE ASOCIADO UN PROYECTO
        if sale_order.simulation_cost_ids:
            if not sale_order.project2_id:
                raise orm.except_orm(_('Project Creation Error'),
                                     _('Project not found'))
            else:
                # SI EL PEDIDO DE VENTA TIENE UN PROYECTO ASOCIADO, COJO
                # SU ID
                project_id = sale_order.project2_id.id
                # Ahora cojo su cuenta analítica
                project = project_obj.browse(cr, uid, project_id,
                                             context=context)
                paccount_id = project.analytic_account_id
                account_analytic_account_id = paccount_id.id

        # SI EL PEDIDO DE VENTA NO VIENE DE UNA SIMULACION, HAGO EL
        # TRATAMIENTO DE ANTES
        if not sale_order.simulation_cost_ids:
            # Llamo con SUPER al método padre
            task_id = super(
                ProcurementOrder, self)._create_service_task(
                    cr, uid, procurement, context=context)
            return task_id

        product = product_obj.browse(cr, uid, procurement.product_id,
                                     context=context)
        # SI EL PEDIDO DE VENTA VIENE DE UNA SIMULACION
        if not sale_order_line.simulation_cost_line_ids:
            # SI LA LINEA DEL PEDIDO DE VENTA NO VIENE DE UNA LINEA DE
            # SIMULACION DE COSTE
            #
            # Llamo a esta función para validar el subproyecto, y
            # aprovecho para imputar en cuenta y eb subcuenta
            # analítica, los costes y beneficios estimados, parámetro
            # type=1 significa que la línea del pedido de venta no
            # viene de simulación de costes
            w_sale_order_partner_id = sale_order.partner_id.id
            w_sale_order_name = sale_order.name
            w_template_id = 0
            w_account_id = account_analytic_account_id
            w_imp_purchase = planned_hours * product.standard_price
            w_imp_sale = planned_hours * product.list_price
            w_type = 1
            spro_id = self._projectval_subproject_account(
                cr, uid, w_type, w_sale_order_name,
                w_sale_order_partner_id, w_simulation_cost_id,
                w_template_id, w_account_id, w_imp_purchase,
                w_imp_sale, context=context)
            # DOY DE ALTA LA TAREA PARA EL SUBPROYECTO
            name = '%s:%s' % (procurement.origin or '',
                              procurement.product_id.name)
            manager = procurement.product_id.product_manager
            vals = {'name': name,
                    'date_deadline': procurement.date_planned,
                    'planned_hours': planned_hours,
                    'remaining_hours': planned_hours,
                    'user_id': manager.id,
                    'notes': procurement.note,
                    'procurement_id': procurement.id,
                    'description': procurement.note,
                    'project_id':  spro_id,
                    'project3_id': project_id,
                    'company_id': procurement.company_id.id,
                    }
            task_id = task_obj.create(cr, uid, vals, context=context)
            vals = {'task_id': task_id,
                    'state': 'running'
                    }
            self.write(cr, uid, [procurement.id], vals,
                       context=context)
            self.project_task_create_note(cr, uid, [procurement.id],
                                          context=context)
        else:
            # SI LA LINEA DEL PEDIDO DE VENTA, VIENE DE UNA LINEA DE
            # SIMULACIÓN DE COSTE, TRATO TODAS LA LINEAS DE SIMULACION
            # DE COSTE
            for line in sale_order_line.simulation_cost_line_ids:
                # Si la linea de simulación de coste, se corresponde
                # con la linea de simulación de coste perteneciente a
                # la simulación de coste activa o a la última
                # historificada, trato la linea.
                if line.simulation_cost_id.id == w_simulation_cost_id:
                    # SI LA LINEA DE SIMULACIÓN DE COSTE, NO VIENE DE
                    # UNA LINEA DE PLANTILLA DE SIMULACION
                    if not line.template_id:
                        cost_product = product_obj.browse(
                            cr, uid, line.product_id.id,
                            context=context)
                        # Llamo a esta función para validar el
                        # subproyecto, y provecho para imputar en
                        # cuenta y eb subcuenta analítica, los costes
                        # y beneficios estimados, parámetro type=2
                        # significa que la línea del pedido de venta
                        # viene de simulación de coste, pero la línea
                        # de simulación de coste de la que viene, no
                        # está asociada a  ninguna plantilla de
                        # simulación
                        partner_id = sale_order.partner_id.id
                        w_sale_order_partner_id = partner_id
                        w_sale_order_name = sale_order.name
                        w_template_id = 0
                        w_account_id = account_analytic_account_id
                        w_imp_purchase = line.subtotal_purchase
                        w_imp_sale = line.subtotal_sale
                        w_type = 2
                        spro_id = self._projectval_subproject_account(
                            cr, uid, w_type, w_sale_order_name,
                            w_sale_order_partner_id,
                            w_simulation_cost_id, w_template_id,
                            w_account_id, w_imp_purchase, w_imp_sale,
                            context=context)
                    else:
                        # SI LA LINEA DE SIMULACIÓN DE COSTE VIENE DE
                        # UNA LINEA DE PLANTILLA DE SIMULACION
                        # Llamo a esta función para validar el
                        # subproyecto, y provecho para imputar en
                        # cuenta y eb subcuenta analítica, los costes
                        # y beneficios estimados, parámetro type=3
                        # significa que la línea del pedido de venta
                        # viene de simulación de coste, y que la línea
                        # de simulación de coste de la que viene, está
                        # asociada a línea de plantilla de simulación
                        partner_id = sale_order.partner_id.id
                        w_sale_order_partner_id = partner_id
                        w_sale_order_name = sale_order.name
                        w_template_id = line.template_id.id
                        w_account_id = account_analytic_account_id
                        w_imp_purchase = line.subtotal_purchase
                        w_imp_sale = line.subtotal_sale
                        w_type = 3
                        spro_id = self._projectval_subproject_account(
                            cr, uid, w_type, w_sale_order_name,
                            w_sale_order_partner_id,
                            w_simulation_cost_id, w_template_id,
                            w_account_id, w_imp_purchase, w_imp_sale,
                            context=context)
                    # COJO EL NOMBRE DEL PRODUCTO DE VENTA DE LA LINEA
                    # DE SIMULACION DE COSTES
                    cost_product = product_obj.browse(
                        cr, uid, line.product_id.id, context=context)
                    costproduct = cost_product.product_tmpl_id
                    sale_product = product_obj.browse(
                        cr, uid, line.product_sale_id.id,
                        context=context)
                    saleproduct = sale_product.product_tmpl_id
                    # DOY DE ALTA LA TAREA PARA EL SUBPROYECTO
                    manager = (line.product_id.product_tmpl_id.product_manager
                               or False)
                    manager_id = False
                    if manager:
                        manager_id = manager.id
                    vals = {'name': line.name,
                            'date_deadline': procurement.date_planned,
                            'planned_hours': line.amount,
                            'remaining_hours': line.amount,
                            'user_id': manager_id,
                            'procurement_id': procurement.id,
                            'description': procurement.name + '\n',
                            'project_id':  spro_id,
                            'project3_id': project_id,
                            'company_id': procurement.company_id.id,
                            'cost_product_name': costproduct.name,
                            'sale_product_name': saleproduct.name,
                            }
                    task_id = task_obj.create(cr, uid, vals,
                                              context=context)
                    vals = {'task_id': task_id,
                            'state': 'running'
                            }
                    self.write(cr, uid, [procurement.id], vals,
                               context=context)
                    self.project_task_create_note(cr, uid, [procurement.id],
                                                  context=context)
        return task_id

    # Funcion para validar que existe la subcuenta analitica, si no existe la
    # subcuenta analitica la crea, y tambien crea su subproyecto. En esta
    # funcion tambien se realiza la imputacion de la estimacion de costes y
    # beneficios en la subcuenta analitica
    def _projectval_subproject_account(self, cr, uid, w_type,
                                       w_sale_order_name,
                                       w_sale_order_partner_id,
                                       w_simulation_cost_id, w_template_id,
                                       w_account_analytic_account_id,
                                       w_imp_purchase, w_imp_sale,
                                       context=None):
        simulation_cost_obj = self.pool['simulation.cost']
        simulation_template_obj = self.pool['simulation.template']
        account_obj = self.pool['account.analytic.account']
        project_obj = self.pool['project.project']
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
        # type=3 significa que la línea del pedido de venta viene de simulación
        # de coste, y que la línea de simulación de coste de la que viene, esta
        # asociada a línea de plantilla de simulación
        if w_type == 3:
            # Cojo el nombre de la plantilla de simulación
            simulation_template = simulation_template_obj.browse(
                cr, uid, w_template_id, context=context)
            # Genero el literal a buscar
            w_literal = ('SUBP ' + simulation_cost.simulation_number + ' / ' +
                         simulation_template.name + ' / ' + w_sale_order_name)
        # CON EL LITERAL GENERADO, BUSCO LA SUBCUENTA ANALÍTICA PARA VER SI
        # EXISTE O NO
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
                raise orm.except_orm(_('Project Creation Error'),
                                     _('Subaccount analytic account not found,'
                                       ' literal: %s') % w_literal)
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
        w_literal2 = w_literal + ' (Internal Task)'
        condition = [('name', '=', w_literal2),
                     ('parent_id', '=', sub_account_analytic_account_id)]
        account_ids3 = account_obj.search(cr, uid, condition, context=context)
        if account_ids3:
            # Si ha encontrado alguna linea, solo habrá encontrado 1, ya que
            # esta buscado una cuenta en concreto, así que me  quedo con su ID
            account_id2 = account_ids3[0]
            condition = [('name', '=', w_literal2)]
            project_id = project_obj.search(cr, uid, condition,
                                            context=context)
            if not project_id:
                raise orm.except_orm(_('Project Creation Error'),
                                     _('subproject not found(2), literal: '
                                       '%s') % w_literal2)
            else:
                subproject_id = project_id[0]
        else:
            if w_type == 3:
                raise orm.except_orm(_('Project Creation Error'),
                                     _('Subaccount Analytic for tab not '
                                       'found(1), literal: %s') % w_literal2)
            else:
                # Doy de alta el subproyecto
                line = {'name': w_literal,
                        'parent_id': w_account_analytic_account_id,
                        'partner_id':  w_sale_order_partner_id,
                        }
                subproject_id = project_obj.create(cr, uid, line,
                                                   context=context)
                # Actualizo la subcuenta analitica creada desde el suproyecto
                subproject = project_obj.browse(cr, uid, subproject_id)
                w_saccount_id = subproject.analytic_account_id.id
                vals = {'name': w_literal,
                        'type': 'normal',
                        'state': 'open',
                        'estimated_balance': 0,
                        'estimated_cost': 0,
                        'estimated_sale': 0,
                        }
                account_obj.write(cr, uid, [w_saccount_id], vals,
                                  context=context)
                line = {'name': w_literal2,
                        'parent_id':  w_saccount_id,
                        'type': 'normal',
                        'state': 'open',
                        'estimated_balance': 0,
                        'estimated_cost': 0,
                        'estimated_sale': 0,
                        }
                account_id2 = account_obj.create(cr, uid, line,
                                                 context=context)
                # ahora creo el subproyecto
                line = {'name': w_literal2,
                        'analytic_account_id': account_id2,
                        }
                subproject_id = project_obj.create(cr, uid, line,
                                                   context=context)

        # UNA VEZ LLEGADO A ESTE PUNTO, YA PUEDO HACER LA IMPUTACION DE LAS
        # ESTIMACIONES A LA SUBCUENTA ANALITICA PERTENECIENTE A LA PESTAÑA DE
        # LA SIMULACION DE COSTES
        sub_account_analytic_account2 = account_obj.browse(
            cr, uid, account_id2, context=context)
        w_estimated_cost = sub_account_analytic_account2.estimated_cost
        w_estimated_cost = w_estimated_cost + w_imp_purchase
        w_estimated_sale = sub_account_analytic_account2.estimated_sale
        w_estimated_sale = w_estimated_sale + w_imp_sale
        w_estimated_balance = w_estimated_sale - w_estimated_cost
        vals = {'estimated_cost': w_estimated_cost,
                'estimated_sale': w_estimated_sale,
                'estimated_balance': w_estimated_balance
                }
        account_obj.write(cr, uid, [account_id2], vals, context=context)

        return subproject_id
