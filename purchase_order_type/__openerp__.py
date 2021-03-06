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

{
    "name": "Purchase order type",
    "version": "1.0",
    "author": "Avanzosc, S.L",
    "category": "Custom Modules",
    "website": "www.avanzosc.es",
    "depends": [
        'purchase'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/purchase_type_data.xml',
        'views/purchase_order_type_view.xml',
    ],
    'installable': True,
}
