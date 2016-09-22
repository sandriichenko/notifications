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
import ddt
from oslo_config import cfg
from oslo_messaging._drivers import common
from oslo_messaging import transport

from tempest.api.baremetal.admin.base import BaseBaremetalTest
from tempest.lib.common.utils import data_utils
from ironic_tempest_plugin import clients

CREATE = 'create'
POWER_STATE = 'power-state'
PROVISION_STATE = 'provision-state'
MAINTENANCE = 'maintenance'
DELETE = 'delete'
UPDATE = 'update'

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


@ddt.ddt
class BaremetalNotifications(BaseBaremetalTest):
    '''Tests for ironic notifications'''

    def setUp(self):
        super(BaremetalNotifications, self).setUp()
        self._expected_notifications = None
        self.exchange = kombu.Exchange('ironic', 'topic', durable=False)
        self.conn = kombu.Connection(get_url(
            transport.get_transport(cfg.CONF).conf))
        self.channel = self.conn.channel()

    @classmethod
    def setup_clients(cls):
        super(BaremetalNotifications, cls).setup_clients()
        cls.baremetal_client = clients.Manager().baremetal_client

    def _define_queue(self, action_type):
        key_level = 'info'
        if action_type == UPDATE:
            key_level = 'debug'
        routing_key = 'ironic_versioned_notifications.{}'.format(key_level)

        queue = kombu.Queue(exchange=self.exchange,
                            routing_key=routing_key,
                            exclusive=True)
        self.queue = queue(self.channel)
        self.queue.declare()

    @ddt.data(CREATE,
              POWER_STATE,
              PROVISION_STATE,
              MAINTENANCE,
              DELETE,
              UPDATE)
    def test_baremetal_notifications_node(self, action_type):
        self._define_queue(action_type)
        _, node = self.create_node(None)
        self._do_action(node['uuid'], action_type)
        notifications = self._capture_notifications(node['uuid'])
        self.assertSequenceIn(self._expected_notifications, notifications)

    def assertSequenceIn(self, expected, actual):
        expected = list(expected)
        actual = list(actual)

        absent = []
        for e in expected:
            if e not in actual:
                absent.append(e)

        assert not absent, "There are absent elements: {}".format(absent)

    def _do_action(self, node_uuid, action_type):
        if action_type == CREATE:
            self._expected_notifications = ['baremetal.node.create.success']

        elif action_type == POWER_STATE:
            self.baremetal_client.set_node_power_state(node_uuid,
                                                       'power off')
            self._expected_notifications = ['baremetal.node.power_set.start',
                                            'baremetal.node.power_set.end']

        elif action_type == PROVISION_STATE:
            for provision_state in ['active', 'deleted']:
                self.baremetal_client.set_node_provision_state(node_uuid,
                                                               provision_state)
            self._expected_notifications = ['baremetal.node.provision_set.start',
                                            'baremetal.node.provision_set.end']

        elif action_type == MAINTENANCE:
            self.baremetal_client.set_maintenance(node_uuid)
            self._expected_notifications = ['baremetal.node.maintenance_set.success']

        elif action_type == DELETE:
            self.delete_node(node_uuid)
            self._expected_notifications = ['baremetal.node.delete.success']

        elif action_type == UPDATE:
            self.baremetal_client.update_node(
                node_uuid, instance_uuid=data_utils.rand_uuid())
            self.addCleanup(self.baremetal_client.update_node, uuid=node_uuid,
                            instance_uuid=None)
            self._expected_notifications = ['baremetal.node.update.success']

        else:
            raise Exception("Undefined action type {!r}".format(action_type))

    def _capture_notifications(self, object_uuid):
        handler = NotificationHandler(object_uuid)

        with self.conn.Consumer(self.queue,
                                callbacks=[handler.process_message],
                                auto_declare=False):
            try:
                while True:
                    self.conn.drain_events(timeout=1)
            except socket.timeout:
                pass

        return handler.notifications
