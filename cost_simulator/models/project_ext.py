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


class Project(orm.Model):
    _inherit = 'project.project'

    _columns = {
        # Campo para saber los pedidos de compra relacionados con el
        # subsubprojecto
        'purchase_order_ids': fields.one2many('purchase.order', 'project2_id',
                                              'Project Purchase Orders'),
        # Campo para saber con que pedido de venta esta relacionado el
        # proyecto
        'sale_order_ids': fields.one2many('sale.order', 'project2_id',
                                          'Project tasks'),
        # Campo para saber con que siulcion esta relacionado el projecto
        'simulation_cost_id': fields.many2one('simulation.cost',
                                              'Simulation Cost'),
        # Campo para saber con que siulcion esta relacionado el subproyecto
        'simulation_cost_id2': fields.many2one('simulation.cost',
                                               'Simulation Cost'),
        # Campo para saber si es un proyecto
        'is_project': fields.boolean('Is Project'),
        # Campo para saber los pedidos de compra relacionados con el proyecto
        'purchase_order_ids2': fields.one2many('purchase.order', 'project3_id',
                                               'Project Purchase Orders'),
        # Campo para saber con que tareas esta relacionados con el proyecto
        'task_ids2': fields.one2many('project.task', 'project3_id',
                                     'Project Task'),
        # Campo para saber si es un subprojecto
        'is_subproject': fields.boolean('Is Subproject'),
    }

    def button_analytical_structure_update_costs(self, cr, uid, ids, *args):
        return True

    def onchange_purchase_ids(self, cr, uid, ids, purchase_list, context=None):
        res = {}
        return {'value': res}


class ProjectTask(orm.Model):
    _inherit = 'project.task'

    _columns = {
        # Nombre del producto de coste de la linea de simulación de costes
        'cost_product_name': fields.char('Cost Product', size=64,
                                         readonly=True),
        # Nombre del producto de venta de la linea de simulación de costes
        'sale_product_name': fields.char('Sale Product', size=64,
                                         readonly=True),
        # Campo para saber con que proyecto esta relacionado la tarea
        'project3_id': fields.many2one('project.project', 'Project'),
    }
