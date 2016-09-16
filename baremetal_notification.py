#
# Copyright 2014 Hewlett-Packard Development Company, L.P.
#
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


import kombu
from oslo_config import cfg
from oslo_messaging._drivers import common
from oslo_messaging import transport



from tempest.api.baremetal.admin.base import BaseBaremetalTest
from oslo_messaging._drivers import common
from ironic_tempest_plugin.tests.scenario import baremetal_manager
from ironic_tempest_plugin import clients

def get_url(conf):
    conf = conf.oslo_messaging_rabbit
    return 'amqp://%s:%s@%s:%s/' % (conf.rabbit_userid,
                                    conf.rabbit_password,
                                    conf.rabbit_host,
                                    conf.rabbit_port)
class NotificationHandler(object):
    def __init__(self, stack_id, events=None):
        self._notifications = []
        self.stack_id = stack_id

    def process_message(self, body, message):
        notification = common.deserialize_msg(body)
        if notification['payload']["ironic_object.data"]['uuid'] == self.stack_id:
            self.notifications.append(notification['event_type'])
        message.ack()

    def clear(self):
        self._notifications = []

    @property
    def notifications(self):
        return self._notifications


class BaremetalNotifications(BaseBaremetalTest):
    def setUp(self):
        super(BaremetalNotifications, self).setUp()
        self.exchange = kombu.Exchange('ironic', 'topic', durable=False)
        queue = kombu.Queue(exchange=self.exchange,
                            routing_key='ironic_versioned_notifications.info',
                            exclusive=True)
        self.conn = kombu.Connection(get_url(
            transport.get_transport(cfg.CONF).conf))
        self.ch = self.conn.channel()
        self.queue = queue(self.ch)
        self.queue.declare()

    @classmethod
    def setup_clients(cls):
        super(BaremetalNotifications, cls).setup_clients()
        cls.baremetal_client = clients.Manager().baremetal_client

    def test_baremetal_server_ops(self):
        _, chassis = self.create_chassis()
        _, node = self.create_node(chassis['uuid'])

        handler = NotificationHandler(node['uuid'])


        #import pdb; pdb.set_trace()
        #print node
        chassis_uuid = 'd504b075-740e-4e56-9782-f8ed1093c8d0'
        #print
        ## print self.baremetal_client.set_node_provision_state(node['uuid'], manage)
        self.baremetal_client.update_node(node['uuid'], add=chassis_uuid)
        #print
        #print node
        handler = NotificationHandler(chassis['uuid'])
        with self.conn.Consumer(self.queue,
                                callbacks=[handler.process_message],
                                auto_declare=False):
            try:
                while True:
                    self.conn.drain_events(timeout=1)
            except Exception:
                pass

        print handler.notifications
        ## for n in BASIC_NOTIFICATIONS:
        ##     self.assertIn(n, handler.notifications)
