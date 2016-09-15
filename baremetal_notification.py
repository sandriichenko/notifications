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
        self.events = events

    def process_message(self, body, message):
        notification = common.deserialize_msg(body)
        if notification['payload']['stack_name'] == self.stack_id:
            if self.events is not None:
                if notification['event_type'] in self.events:
                    self.notifications.append(notification['event_type'])
            else:
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
                            routing_key='notifications.info',
                            exclusive=True)
        self.conn = kombu.Connection(get_url(
            transport.get_transport(cfg.CONF).conf))
        self.ch = self.conn.channel()
        self.queue = queue(self.ch)
        self.queue.declare()

    def test_baremetal_server_ops(self):
        _, chassis = self.create_chassis()
        uuid = chassis['uuid']
        _, node = self.create_node(uuid)
        print node
