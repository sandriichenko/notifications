# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import socket
import kombu
from oslo_config import cfg
from oslo_messaging._drivers import common
from oslo_messaging import transport

from tempest.api.baremetal.admin.base import BaseBaremetalTest
from tempest.lib.common.utils import data_utils
from ironic_tempest_plugin import clients


BASIC_NOTIFICATIONS_NODE = [
    'baremetal.node.create.success',
    'baremetal.node.delete.success',
    'baremetal.node.provision_set.success',
    'baremetal.node.power_set.start',
    'baremetal.node.power_set.end',
    'baremetal.node.provision_set.start',
    'baremetal.node.provision_set.end',
    'baremetal.node.maintenance_set.success'
]

BASIC_NOTIFICATIONS_PORT = [
    'baremetal.port.create.success',
    'baremetal.port.delete.success'
]

BASIC_NOTIFICATIONS_CHASSIS = [
    'baremetal.chassis.create.success',
    'baremetal.chassis.delete.success'
]


def get_url(conf):
    conf = conf.oslo_messaging_rabbit
    return 'amqp://{0}:{1}@{2}:{3}/'.format(conf.rabbit_userid,
                                            conf.rabbit_password,
                                            conf.rabbit_host,
                                            conf.rabbit_port)
class NotificationHandler(object):

    def __init__(self, uuid):
        self._notifications = []
        self.uuid = uuid

    def process_message(self, body, message):
        notification = common.deserialize_msg(body)
        if notification['payload']["ironic_object.data"]['uuid'] == self.uuid:
            self.notifications.append(notification['event_type'])
        message.ack()

    def clear(self):
        self._notifications = []

    @property
    def notifications(self):
        return self._notifications


class BaremetalNotifications(BaseBaremetalTest):
    '''Tests for ironic notifications'''

    def setUp(self):
        super(BaremetalNotifications, self).setUp()
        self.exchange = kombu.Exchange('ironic', 'topic', durable=False)
        queue = kombu.Queue(exchange=self.exchange,
                            routing_key='ironic_versioned_notifications.info',
                            exclusive=True)
        self.conn = kombu.Connection(get_url(
            transport.get_transport(cfg.CONF).conf))
        self.channel = self.conn.channel()
        self.queue = queue(self.channel)
        self.queue.declare()

    @classmethod
    def setup_clients(cls):
        super(BaremetalNotifications, cls).setup_clients()
        cls.baremetal_client = clients.Manager().baremetal_client

    def test_baremetal_notifications_node(self):
        resp, node = self.create_node(None)
        provision_states_list = ['active', 'deleted']
        instance_uuid = data_utils.rand_uuid()
        self.baremetal_client.update_node(node['uuid'],
                                          instance_uuid=instance_uuid)
        self.baremetal_client.set_node_power_state(node['uuid'], 'power off')
        for provision_state in provision_states_list:
            self.baremetal_client.set_node_provision_state(node['uuid'],
            provision_state)
        self.baremetal_client.set_maintenance(node['uuid'])
        self.delete_node(node['uuid'])
        handler = NotificationHandler(node['uuid'])

        with self.conn.Consumer(self.queue,
                                callbacks=[handler.process_message],
                                auto_declare=False):
            try:
                while True:
                    self.conn.drain_events(timeout=1)
            except socket.timeout:
                pass
        print handler.notifications
        for notification in BASIC_NOTIFICATIONS_NODE:
            self.assertIn(notification, handler.notifications)

    def test_baremetal_notifications_chassis(self):
        resp, chassis = self.create_chassis()
        new_description = data_utils.rand_name('new-description')
        self.baremetal_client.update_chassis(chassis['uuid'],
                                             description=new_description)
        self.baremetal_client.delete_chassis(chassis['uuid'])

        handler = NotificationHandler(chassis['uuid'])

        with self.conn.Consumer(self.queue,
                                callbacks=[handler.process_message],
                                auto_declare=False):
            try:
                while True:
                    self.conn.drain_events(timeout=1)
            except socket.timeout:
                pass

        for notification in BASIC_NOTIFICATIONS_CHASSIS:
            self.assertIn(notification, handler.notifications)

    def test_baremetal_notifications_port(self):
        resp_node, node = self.create_node(None)
        resp, port = self.create_port(node['uuid'],
                                      data_utils.rand_mac_address())
        patch = [{'path': '/extra/key1',
                  'op': 'add',
                  'value': {'key1': 'value1'}}]
        self.baremetal_client.update_port(port['uuid'], patch)
        self.delete_port(port['uuid'])

        handler = NotificationHandler(port['uuid'])

        with self.conn.Consumer(self.queue,
                                callbacks=[handler.process_message],
                                auto_declare=False):
            try:
                while True:
                    self.conn.drain_events(timeout=1)
            except socket.timeout:
                pass
        print handler.notifications
        for notification in BASIC_NOTIFICATIONS_PORT:
            self.assertIn(notification, handler.notifications)

    def test_baremetal_notifications_test(self):
        resp, node = self.create_node(None)
        self.baremetal_client.set_maintenance(node['uuid'])
